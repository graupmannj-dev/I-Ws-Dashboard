#!/usr/bin/env python3
"""Optional measured map feeds. No credentials are shipped to Pages.

Run once for a dated static snapshot or serve for browser polling. AIS requires
websocket-client (requirements-layers.txt); other collectors use the stdlib.
"""
import argparse
import datetime as dt
import email.utils
import html
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

try:
    from .adsb_lol import collect_region as collect_adsb_lol, SOURCE as ADSB_LOL_SOURCE
except ImportError:
    from adsb_lol import collect_region as collect_adsb_lol, SOURCE as ADSB_LOL_SOURCE

KEYS = ('aircraft', 'ships', 'airspace', 'maritime', 'advisories', 'embassies')
RSS = 'https://travel.state.gov/_res/rss/TAsTWs.xml'
LOCK = threading.Lock()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def empty():
    return {'version': 1, 'generated_at': now(), 'layers': {
        k: {'status': 'not_configured', 'records': [], 'checked_at': None,
            'message': 'Source not connected'} for k in KEYS}}

def request(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'AIBA-Atlas/1.0', **(headers or {})})
    with urllib.request.urlopen(req, timeout=25) as response:
        body = response.read(8_000_001)
        if len(body) > 8_000_000:
            raise ValueError('Source response too large')
        return body

def coord(lon, lat):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (lon, lat)) and -180 <= lon <= 180 and -90 <= lat <= 90

def aircraft(payload):
    stamp = dt.datetime.fromtimestamp(payload['time'], dt.timezone.utc).isoformat()
    rows = []
    for s in payload.get('states') or []:
        if len(s) < 14 or not coord(s[5], s[6]) or not s[3]:
            continue
        rows.append({'id': s[0], 'title': (s[1] or s[0]).strip(), 'lon': s[5], 'lat': s[6],
                     'observed_at': dt.datetime.fromtimestamp(s[3], dt.timezone.utc).isoformat(),
                     'heading': s[10], 'detail': f'Altitude: {s[7]} m; speed: {s[9]} m/s; origin: {s[2]}',
                     'source': 'OpenSky Network', 'url': 'https://opensky-network.org/', 'date': stamp})
    return rows

def advisories(xml):
    rows = []
    for item in ET.fromstring(xml).findall('.//item'):
        title = html.unescape(item.findtext('title') or '')
        match = re.search(r'^(.*?)\s*[-–:]\s*Level\s*([1-4])\b', title, re.I)
        url = item.findtext('link') or ''
        if not match or urllib.parse.urlsplit(url).hostname != 'travel.state.gov':
            continue
        published = item.findtext('pubDate') or ''
        try:
            published = email.utils.parsedate_to_datetime(published).isoformat()
        except (ValueError, TypeError):
            published = None
        rows.append({'id': url, 'country': match[1].strip(), 'level': int(match[2]),
                     'title': title, 'url': url, 'source': 'US Department of State',
                     'date': published, 'detail': re.sub('<[^>]+>', ' ', html.unescape(item.findtext('description') or ''))[:4000]})
    if not rows:
        raise ValueError('No recognized country advisory levels in official RSS')
    return rows

def notices(path, key):
    """Reviewed official notices; allow only explicit source geometry, never inferred areas."""
    value = json.loads(Path(path).read_text())
    rows = value.get(key, [])
    if not isinstance(rows, list):
        raise ValueError('Notice list required')
    for row in rows:
        url = urllib.parse.urlsplit(row['url'])
        if url.scheme != 'https' or not url.hostname or not row.get('source') or not row.get('title'):
            raise ValueError('Each notice requires an HTTPS source, publisher and title')
        if not row.get('id'):
            raise ValueError('Notice ID required')
        if not row.get('valid_until') or not row.get('valid_from'):
            raise ValueError('Notice validity bounds required; unknown end dates must be reviewed before import')
        for field in ('valid_from', 'valid_until'):
            value = dt.datetime.fromisoformat(row[field].replace('Z', '+00:00'))
            if value.tzinfo is None:
                raise ValueError('Timezone required')
        if dt.datetime.fromisoformat(row['valid_until'].replace('Z', '+00:00')) <= dt.datetime.fromisoformat(row['valid_from'].replace('Z', '+00:00')):
            raise ValueError('Notice end must follow start')
        if ('lon' in row or 'lat' in row) and not coord(row.get('lon'), row.get('lat')):
            raise ValueError('Invalid notice position')
        geometry = row.get('geometry')
        if geometry is not None:
            if not isinstance(geometry, dict):
                raise ValueError('Notice geometry must be an object')
            kind = geometry.get('type')
            if kind == 'Circle':
                center, radius = geometry.get('center'), geometry.get('radius_km')
                if (not isinstance(center, list) or len(center) != 2 or
                    not coord(*center) or not isinstance(radius, (int, float)) or
                    isinstance(radius, bool) or not math.isfinite(radius) or
                    not 0 < radius <= 3500):
                    raise ValueError('Circle requires an explicit source center and 0-3500 km radius')
            elif kind in ('BBox', 'Rectangle'):
                corners = geometry.get('coordinates')
                if not isinstance(corners, list) or len(corners) != 2 or not all(
                    isinstance(point, list) and len(point) == 2 and coord(*point)
                    for point in corners
                ):
                    raise ValueError('Coordinate box requires two valid WGS84 corners')
                (west, south), (east, north) = corners
                width = east - west if east >= west else east + 360 - west
                if not south < north or not 0 < width <= 180:
                    raise ValueError('Invalid latitude range or implausible box width')
            elif kind in ('Polygon', 'MultiPolygon', 'LineString'):
                def check(points):
                    if not isinstance(points, list) or not points:
                        raise ValueError('Empty geometry')
                    if isinstance(points[0], (int, float)):
                        if len(points) != 2 or not coord(*points):
                            raise ValueError('Invalid coordinates')
                    else:
                        for child in points:
                            check(child)
                check(geometry.get('coordinates'))
            else:
                raise ValueError('Unsupported notice geometry')
    return rows

TFR = 'https://tfr.faa.gov/tfrapi/exportTfrList?format=json'

def faa_coordinate(text):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([NSEW])', text or '')
    if not match:
        raise ValueError('Unsupported FAA coordinate')
    return float(match[1]) * (-1 if match[2] in 'SW' else 1)

def tfr_detail(xml, entry):
    root = ET.fromstring(xml)
    notam = root.find('.//Not')
    if notam is None or notam.findtext('codeTimeZone') != 'UTC' or notam.findtext('codeExpirationTimeZone', 'UTC') != 'UTC':
        raise ValueError('Expected UTC FAA NOTAM')
    if notam.findtext('codeDailyOper', 'false').lower() == 'true':
        return []
    def utc(text):
        stamp = dt.datetime.fromisoformat(text)
        return stamp.replace(tzinfo=dt.timezone.utc).isoformat()
    rows = []
    for index, area in enumerate(notam.findall('.//TFRAreaGroup')):
        schedules = area.findall('./aseTFRArea/ScheduleGroup')
        # Complex recurring schedules require full AIXM interpretation; do not
        # silently turn them into an always-active restriction.
        if any(n.tag not in ('isTimeSeparate', 'dateEffective', 'dateExpire') for schedule in schedules for n in schedule):
            continue
        rings = []
        for boundary in area.findall('./abdMergedArea'):
            ring = []
            for vertex in boundary.findall('./Avx'):
                if vertex.findtext('codeType') != 'GRC' or vertex.findtext('codeDatum') != 'WGE':
                    raise ValueError('Unsupported non-linear merged FAA boundary')
                point = [faa_coordinate(vertex.findtext('geoLong')), faa_coordinate(vertex.findtext('geoLat'))]
                if not coord(*point):
                    raise ValueError('Invalid FAA position')
                ring.append(point)
            if len(ring) >= 3:
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                rings.append([ring])
        for slot, schedule in enumerate(schedules or [notam]):
            start = schedule.findtext('dateEffective') or notam.findtext('dateEffective')
            end = schedule.findtext('dateExpire') or notam.findtext('dateExpire')
            if not start or not end:
                continue
            row = {'id': entry['notam_id'] + f':{index}:{slot}',
                'title': 'FAA TFR ' + entry['notam_id'] + ' · ' + entry.get('description', ''),
                'source': 'Federal Aviation Administration',
                'url': 'https://tfr.faa.gov/' + entry['notam_id'].replace('/', '_') + '.html',
                'date': notam.findtext('NotUid/dateIssued'),
                'valid_from': utc(start), 'valid_until': utc(end),
                'detail': 'US temporary flight restriction; not worldwide NOTAM coverage. Read the original for altitude, exceptions and full schedule. ' + entry.get('type', '')}
            if rings:
                row['geometry'] = {'type': 'MultiPolygon', 'coordinates': rings}
            rows.append(row)
    return rows

def collect_tfr():
    entries = json.loads(request(TFR))
    if not isinstance(entries, list):
        raise ValueError('Expected FAA TFR list')
    def one(entry):
        identity = entry['notam_id']
        if not re.fullmatch(r'\d/\d{4}', identity):
            raise ValueError('Unexpected NOTAM identifier')
        try:
            rows = tfr_detail(request('https://tfr.faa.gov/download/detail_' + identity.replace('/', '_') + '.xml'), entry)
            return rows, not bool(rows)
        except (ValueError, OSError, ET.ParseError):
            return [], True
    # Fail visibly rather than implying complete coverage after partial downloads.
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, entries))
    rows = [row for result, _ in results for row in result]
    if entries and not rows:
        raise ValueError('No supported FAA notices')
    return {'records': rows, 'skipped': sum(int(skipped) for _, skipped in results)}


NIORD = 'https://niord.dma.dk/rest/public/v1/messages?domain=niord-nw&domain=niord-fe'

def maritime(payload):
    if not isinstance(payload, list):
        raise ValueError('Expected Danish Maritime Authority notice list')
    rows = []
    for message in payload:
        if message.get('status') != 'PUBLISHED':
            continue
        english = next((d for d in message.get('descs', []) if d.get('lang') == 'en'), {})
        title = english.get('title', '')
        # Include only explicit restriction notices, not every buoy outage.
        if not re.search(r'\b(closed|prohibited|restricted|exclusion|firing exercise[s]?|gunnery|live.?fire|military exercise[s]?)\b', title, re.I):
            continue
        for i, part in enumerate(message.get('parts', [])):
            description = next((d for d in part.get('descs', []) if d.get('lang') == 'en'), {})
            features = (part.get('geometry') or {}).get('features', [])
            for j, event in enumerate(part.get('eventDates') or [{}]):
                def stamp(ms):
                    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat() if ms else None
                row = {'id': f"{message['id']}:{i}:{j}", 'title': title,
                    'source': 'Danish Maritime Authority — regional coverage only',
                    'url': 'https://niord.dma.dk/#/message/' + message['id'],
                    'date': stamp(message.get('updated')), 'valid_from': stamp(event.get('fromDate') or message.get('publishDateFrom')),
                    'valid_until': stamp(event.get('toDate') or message.get('publishDateTo')),
                    'in_force': True,
                    'detail': re.sub('<[^>]+>', ' ', html.unescape(description.get('details', ''))) +
                        ' Published navigational restriction; no worldwide sea-lane closure coverage. Open-ended notices are rechecked with the source.'}
                # Preserve each published feature rather than inventing an area.
                for k, feature in enumerate(features or [{}]):
                    item = {**row, 'id': row['id'] + ':' + str(k)}
                    geo = feature.get('geometry') or {}
                    if geo.get('type') == 'Point' and coord(*geo['coordinates']):
                        item['lon'], item['lat'] = geo['coordinates']
                    elif geo.get('type') in ('Polygon', 'MultiPolygon', 'LineString'):
                        item['geometry'] = geo
                    rows.append(item)
    return rows

def embassy_mentions(xml):
    rows = []
    for advisory in advisories(xml):
        matches = []
        # Surface source wording as a notice, never classify a full evacuation
        # or current embassy operations from an unstructured keyword match.
        for phrase in ('ordered departure', 'authorized departure', 'suspended operations', 'suspended its operations'):
            text = advisory['detail'].lower()
            at = text.find(phrase)
            if at >= 0:
                matches.append(advisory['detail'][max(0, at-120):at+400])
        if matches:
            rows.append({**advisory, 'id': 'embassy:' + advisory['id'],
                'title': advisory['country'] + ' · Departure/operations notice — review source',
                'notice_only': True, 'detail': 'Official advisory contains departure, operations or evacuation wording; this is not a verified current embassy staffing classification. ' + ' … '.join(matches)})
    return rows


class Collector:
    def __init__(self, reviewed=None):
        self.payload = empty()
        self.reviewed = reviewed
        self.token = None
        self.token_until = 0

    def update(self, key, load, source):
        try:
            result = load()
            partial = isinstance(result, dict)
            records = result['records'] if partial else result
            if not isinstance(records, list) or len(records) > 3000:
                raise ValueError('Invalid or oversized layer response')
            skipped = result.get('skipped', 0) if partial else 0
            if not isinstance(skipped, int) or isinstance(skipped, bool) or skipped < 0:
                raise ValueError('Invalid source exclusion count')
            if key in ('aircraft', 'ships'):
                # No stale historical snapshots accepted as live traffic.
                if len(records) > 2500:
                    raise ValueError('Excessive live traffic positions')
            layer = {'status': 'partial' if skipped else 'snapshot',
                     'records': records, 'checked_at': now(), 'source': source,
                     'message': f'{len(records)} supported source records' +
                                (f'; {skipped} excluded/unsupported upstream records; coverage partial'
                                 if skipped else '')}
            if partial and result.get('coverage'):
                layer['message'] += '; ' + str(result['coverage'])[:100]
            if key == 'aircraft' and source == ADSB_LOL_SOURCE:
                layer['attribution'] = 'ADSB.lol contributors · ODbL 1.0'
                layer['license_url'] = 'https://opendatacommons.org/licenses/odbl/1-0/'
        except Exception as exc:
            # Do not retain previously successful measurements as current.
            layer = {'status': 'unavailable', 'records': [], 'checked_at': now(),
                     'source': source, 'message': f'Collection failed ({type(exc).__name__}); source unavailable'}
        with LOCK:
            self.payload['layers'][key] = layer
            self.payload['generated_at'] = now()

    def opensky(self):
        if time.time() >= self.token_until:
            data = urllib.parse.urlencode({'grant_type': 'client_credentials',
                'client_id': os.environ['OPENSKY_CLIENT_ID'],
                'client_secret': os.environ['OPENSKY_CLIENT_SECRET']}).encode()
            token = json.loads(request('https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token', data,
                {'Content-Type': 'application/x-www-form-urlencoded'}))
            self.token = token['access_token']
            self.token_until = time.time() + int(token['expires_in']) - 30
        # A regional bounding box reduces credit use. Format: south,west,north,east.
        south, west, north, east = map(float, os.environ.get('AIBA_TRACK_BBOX', '10,30,45,70').split(','))
        if not coord(west, south) or not coord(east, north) or south >= north or west >= east:
            raise ValueError('Invalid bounding box')
        query = urllib.parse.urlencode(dict(lamin=south, lomin=west, lamax=north, lomax=east))
        return aircraft(json.loads(request('https://opensky-network.org/api/states/all?' + query,
            headers={'Authorization': 'Bearer ' + self.token})))

    def collect(self):
        self.update('advisories', lambda: advisories(request(RSS)), RSS)
        self.update('airspace', collect_tfr, TFR)
        self.update('maritime', lambda: maritime(json.loads(request(NIORD))), NIORD)
        self.update('embassies', lambda: embassy_mentions(request(RSS)), RSS)
        provider = os.environ.get('AIBA_AIRCRAFT_PROVIDER', '').strip().lower()
        if provider == 'adsb_lol':
            self.update('aircraft', lambda: collect_adsb_lol(request), ADSB_LOL_SOURCE)
        elif provider == 'opensky' or (
            not provider and os.environ.get('OPENSKY_CLIENT_ID')
            and os.environ.get('OPENSKY_CLIENT_SECRET')
        ):
            self.update('aircraft', self.opensky, 'https://opensky-network.org/')
        elif provider and provider not in ('none', 'off'):
            self.update('aircraft', lambda: (_ for _ in ()).throw(
                ValueError('Unsupported configured aircraft provider')), 'Aircraft provider configuration')
        if self.reviewed:
            for key in ('maritime', 'embassies'):
                try:
                    imported = notices(self.reviewed, key)
                    with LOCK:
                        layer = self.payload['layers'][key]
                        layer['records'].extend(imported)
                        if imported:
                            if layer['status'] == 'unavailable':
                                layer['status'] = 'partial'
                            layer['checked_at'] = now()
                            layer['message'] += f'; {len(imported)} reviewed notices imported'
                except Exception:
                    with LOCK:
                        self.payload['layers'][key]['message'] += '; reviewed import failed validation'

    def ais(self):
        import websocket
        delay = 2
        while True:
            connection = None
            try:
                south, west, north, east = map(float, os.environ.get('AIBA_TRACK_BBOX', '10,30,45,70').split(','))
                if not coord(west, south) or not coord(east, north) or south >= north or west >= east:
                    raise ValueError('Invalid bounding box')
                connection = websocket.create_connection('wss://stream.aisstream.io/v0/stream', timeout=60)
                connection.send(json.dumps({'APIKey': os.environ['AISSTREAM_API_KEY'],
                    'BoundingBoxes': [[[south, west], [north, east]]],
                    'FilterMessageTypes': ['PositionReport', 'StandardClassBPositionReport', 'ExtendedClassBPositionReport']}))
                ships = {}
                while True:
                    msg = json.loads(connection.recv())
                    if 'error' in msg or 'Error' in msg:
                        raise ValueError('AIS subscription rejected')
                    meta = msg.get('MetaData') or {}
                    body = (msg.get('Message') or {}).get(msg.get('MessageType'), {})
                    lon, lat = body.get('Longitude'), body.get('Latitude')
                    if not coord(lon, lat) or not meta.get('MMSI'):
                        continue
                    stamp = meta.get('time_utc', '')
                    # Provider timestamps sometimes append an explicit UTC label.
                    stamp = stamp.removesuffix(' UTC')
                    observed = dt.datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                    if observed.tzinfo is None:
                        raise ValueError('AIS timestamp missing timezone')
                    identity = str(meta['MMSI'])
                    ships[identity] = {'id': identity, 'title': meta.get('ShipName', '').strip() or identity,
                        'lon': lon, 'lat': lat, 'observed_at': observed.isoformat(),
                        'heading': body.get('Cog'), 'source': 'AISStream', 'url': 'https://aisstream.io/',
                        'detail': f"MMSI: {identity}; speed: {body.get('Sog')} knots", 'date': observed.isoformat()}
                    cutoff = time.time() - 600
                    ships = {k: v for k, v in ships.items() if dt.datetime.fromisoformat(v['observed_at']).timestamp() > cutoff}
                    with LOCK:
                        self.payload['layers']['ships'] = {'status': 'streaming', 'checked_at': now(),
                            'message': f'{len(ships)} recently observed vessels', 'records': list(ships.values())[:10000]}
                    delay = 2
            except Exception:
                with LOCK:
                    self.payload['layers']['ships'] = {'status': 'unavailable', 'checked_at': now(),
                        'message': 'AIS connection interrupted; reconnecting', 'records': []}
                time.sleep(delay)
                delay = min(delay * 2, 60)
            finally:
                if connection:
                    connection.close()

    def snapshot(self):
        with LOCK:
            return json.dumps(self.payload, allow_nan=False).encode()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=Path('_site/layers.json'))
    p.add_argument('--reviewed', type=Path)
    p.add_argument('--serve', type=Path, help='Serve this built site plus /api/layers on localhost')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--bind', default='127.0.0.1')
    p.add_argument('--interval', type=int, default=300,
                   help='Configured aircraft/official source refresh seconds; ADSB.lol minimum 300')
    args = p.parse_args()
    collector = Collector(args.reviewed)
    collector.collect()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(collector.snapshot())
    if not args.serve:
        print('Wrote dated layer snapshot:', args.output)
        return
    def refresh():
        while True:
            time.sleep(max(300 if os.environ.get('AIBA_AIRCRAFT_PROVIDER', '').lower() == 'adsb_lol'
                               else 60, args.interval))
            collector.collect()
    threading.Thread(target=refresh, daemon=True).start()
    if os.environ.get('AISSTREAM_API_KEY'):
        import websocket  # Fail clearly at startup if optional dependency is missing.
        threading.Thread(target=collector.ais, daemon=True).start()
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(args.serve.resolve()), **kw)
        def do_GET(self):
            if self.path.split('?')[0] == '/api/layers':
                data = collector.snapshot()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                origin = os.environ.get('AIBA_ALLOWED_ORIGIN')
                if origin:
                    self.send_header('Access-Control-Allow-Origin', origin)
                    self.send_header('Vary', 'Origin')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                super().do_GET()
    print(f'Atlas live preview: http://127.0.0.1:{args.port}/')
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()

if __name__ == '__main__':
    main()
