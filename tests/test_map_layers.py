import json
from pathlib import Path
import tempfile
import unittest
from dashboard.collect_layers import aircraft, advisories, coord, notices, tfr_detail, maritime, embassy_mentions, Collector

class MapLayersTest(unittest.TestCase):
    def test_aircraft_uses_position_time_and_rejects_missing_coordinates(self):
        row = ['abc', 'TEST  ', 'US', 1700000000, 1700000005, 45, 25, 3000, False, 100, 90, 0, None, 3000]
        result = aircraft({'time':1700000010, 'states':[row, [*row[:5], None, *row[6:]]]})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['observed_at'], '2023-11-14T22:13:20+00:00')
        self.assertFalse(coord(float('nan'), 20))
        self.assertFalse(coord(True, 20))

    def test_advisory_levels_and_departures_are_separate(self):
        xml = b'''<rss><channel><item><title>Example - Level 4: Do Not Travel</title>
        <link>https://travel.state.gov/example</link><pubDate>Sat, 07 Nov 2026 12:00:00 GMT</pubDate>
        <description>Ordered departure. See full source.</description></item></channel></rss>'''
        rows = advisories(xml)
        self.assertEqual(rows[0]['level'], 4)
        self.assertEqual(rows[0]['country'], 'Example')
        mention = embassy_mentions(xml)[0]
        self.assertTrue(mention['notice_only'])
        self.assertIn('not a verified current', mention['detail'])
        with self.assertRaises(ValueError):
            advisories(xml.replace(b'travel.state.gov', b'example.com'))
        self.assertEqual(embassy_mentions(xml.replace(b'Ordered departure', b'Do not rely on evacuation')), [])

    def test_faa_coordinates_validity_and_schedule(self):
        xml = b'''<root><Not><codeTimeZone>UTC</codeTimeZone><dateEffective>2026-11-07T10:00:00</dateEffective>
        <dateExpire>2026-11-07T12:00:00</dateExpire><TFRAreaGroup><abdMergedArea>
        <Avx><codeType>GRC</codeType><codeDatum>WGE</codeDatum><geoLat>25N</geoLat><geoLong>045W</geoLong></Avx>
        <Avx><codeType>GRC</codeType><codeDatum>WGE</codeDatum><geoLat>26N</geoLat><geoLong>045W</geoLong></Avx>
        <Avx><codeType>GRC</codeType><codeDatum>WGE</codeDatum><geoLat>25N</geoLat><geoLong>044W</geoLong></Avx>
        </abdMergedArea></TFRAreaGroup></Not></root>'''
        row = tfr_detail(xml, {'notam_id':'6/1234'})[0]
        ring = row['geometry']['coordinates'][0][0]
        self.assertEqual(ring[0], [-45,25])
        self.assertEqual(ring[0], ring[-1])
        self.assertTrue(row['valid_until'].endswith('+00:00'))
        with self.assertRaises(ValueError):
            tfr_detail(xml.replace(b'UTC', b'EST'), {'notam_id':'6/1234'})

    def test_import_requires_validity_and_valid_geometry(self):
        row = {'id':'closure', 'title':'Closure', 'source':'Authority', 'url':'https://example.org/notice',
               'valid_from':'2026-11-07T10:00:00Z', 'valid_until':'2026-11-07T12:00:00Z',
               'geometry':{'type':'Polygon', 'coordinates':[[[200, 20]]]}}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'notices.json'
            p.write_text(json.dumps({'maritime':[row]}))
            with self.assertRaises(ValueError):
                notices(p, 'maritime')

    def test_reviewed_source_defined_circles_and_boxes(self):
        base = {'id':'notice-1', 'title':'Official temporary restriction',
                'source':'Fictional authority (synthetic test)', 'url':'https://example.org/notice',
                'valid_from':'2026-11-07T10:00:00Z','valid_until':'2026-11-09T12:00:00Z'}
        area = {**base, 'geometry':{'type':'Circle','center':[52.0,20.0],'radius_km':220}}
        rectangle = {**base,'id':'notice-2',
                     'geometry':{'type':'BBox','coordinates':[[177,10],[-178,15]]}}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'areas.json'
            def valid(rows):
                p.write_text(json.dumps({'airspace':rows}))
                return notices(p, 'airspace')
            self.assertEqual(len(valid([area, rectangle])),2)
            for bad_radius in [-1, 0, 3501, float('nan'), True]:
                with self.subTest(radius=bad_radius):
                    with self.assertRaises(ValueError):
                        valid([{**area,'geometry':{**area['geometry'],'radius_km':bad_radius}}])
            for invalid_box in [
                [[52,22],[50,19]], # reverse latitude
                [[-175,10],[175,15]], # exceeds 180 degree width
                [[190,10],[191,12]], # invalid longitude
            ]:
                with self.subTest(box=invalid_box):
                    with self.assertRaises(ValueError):
                        valid([{**rectangle,'geometry':{'type':'BBox','coordinates':invalid_box}}])
            with self.assertRaises(ValueError):
                valid([{**area,'geometry':{'type':'Circle','center':[52,91],
                                          'radius_km':100}}])

    def test_source_failure_clears_old_measurements(self):
        c = Collector()
        c.update('aircraft', lambda:[{'id':'old'}], 'test')
        def fail():
            raise ValueError('secret must not be emitted')
        c.update('aircraft', fail, 'test')
        layer = c.payload['layers']['aircraft']
        self.assertEqual(layer['records'], [])
        self.assertEqual(layer['status'], 'unavailable')
        self.assertNotIn('secret', layer['message'])

    def test_maritime_only_published_explicit_restrictions(self):
        base = {'id':'one','status':'PUBLISHED','descs':[{'lang':'en','title':'Entrance closed for traffic'}],
                'publishDateFrom':1700000000000, 'parts':[{'eventDates':[{'fromDate':1700000000000}],
                    'geometry':{'features':[{'geometry':{'type':'Point','coordinates':[10,55]}}]}}]}
        rows = maritime([base])
        self.assertEqual(rows[0]['lon'],10)
        self.assertIsNone(rows[0]['valid_until'])
        self.assertTrue(rows[0]['in_force'])
        self.assertEqual(maritime([{**base,'status':'CANCELLED'}]), [])
        self.assertEqual(maritime([{**base,'descs':[{'lang':'en','title':'Light buoy unlit'}]}]), [])
