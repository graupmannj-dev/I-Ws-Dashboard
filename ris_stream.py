#!/usr/bin/env python3
"""Optional scoped RIPE RIS Live BGP sampler (standalone, NOT always-on hosting).

Does not claim that BGP UPDATEs are hijacks or nation-state cyberattacks.
Requires websocket-client, a small explicit prefix allowlist, and separate
durable publication arrangements when run as a persistent service.
"""
from __future__ import annotations
import argparse
import datetime as dt
import ipaddress
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from friction_pipeline import event_time, iso, utcnow, write_json

ENDPOINT = "wss://ris-live.ripe.net/v1/ws/?client=aiba-scoped-public-iw-v1"
SOURCE = "https://ris-live.ripe.net/"
MAX_PREFIXES = 8
MAX_MESSAGES_PER_WINDOW = 100_000


def allowed_prefixes(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= MAX_PREFIXES:
        raise ValueError("Supply between 1 and 8 explicitly monitored public BGP prefixes")
    prefixes = []
    for raw in values:
        net = ipaddress.ip_network(raw, strict=True)
        # Avoid indiscriminate country-scale or global firehose subscriptions.
        if (net.version == 4 and net.prefixlen < 12) or (net.version == 6 and net.prefixlen < 32):
            raise ValueError("Monitored prefixes must be narrower than /12 IPv4 or /32 IPv6")
        if not net.is_global:
            raise ValueError("Only globally routable public prefixes are supported")
        prefixes.append(net)
    if len(set(prefixes)) != len(prefixes):
        raise ValueError("Duplicate monitored prefixes")
    return prefixes


def subscribed_match(prefix, monitors):
    try:
        observed = ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return []
    return [str(net) for net in monitors
            if observed.version == net.version and observed.subnet_of(net)]


class Window:
    def __init__(self, prefixes, started=None):
        self.monitors = allowed_prefixes(prefixes)
        self.started = started or utcnow()
        self.counts = defaultdict(lambda: {"announcements": 0, "withdrawals": 0,
                                            "origins": Counter(), "collectors": set()})
        self.seen = set()
        self.truncated = False
        self.messages = 0

    def accept(self, envelope):
        if not isinstance(envelope, dict) or envelope.get("type") != "ris_message":
            return
        data = envelope.get("data")
        if not isinstance(data, dict) or data.get("type") != "UPDATE":
            return
        moment = event_time(data.get("timestamp"))
        if not moment or moment < self.started - dt.timedelta(minutes=5):
            return
        msgid = data.get("id")
        if not isinstance(msgid, str) or len(msgid) > 200 or msgid in self.seen:
            return
        if self.messages >= MAX_MESSAGES_PER_WINDOW:
            self.truncated = True
            return
        self.seen.add(msgid)
        self.messages += 1
        host = str(data.get("host") or "")[:24]
        path = data.get("path")
        last_as = path[-1] if isinstance(path, list) and path else None
        origin = str(last_as) if isinstance(last_as, int) else None
        for announcement in data.get("announcements", []) or []:
            if not isinstance(announcement, dict):
                continue
            for raw in announcement.get("prefixes", []) or []:
                for key in subscribed_match(raw, self.monitors):
                    v = self.counts[key]
                    v["announcements"] += 1
                    if host:
                        v["collectors"].add(host)
                    if origin:
                        v["origins"][origin] += 1
        for raw in data.get("withdrawals", []) or []:
            for key in subscribed_match(raw, self.monitors):
                v = self.counts[key]
                v["withdrawals"] += 1
                if host:
                    v["collectors"].add(host)

    def output(self, ended=None, status="collected"):
        ended = ended or utcnow()
        duration = max(0.0, (ended - self.started).total_seconds())
        return {
            "schema_version": 1, "source": "RIPE RIS Live",
            "source_url": SOURCE, "started_at": iso(self.started), "ended_at": iso(ended),
            "coverage_seconds": round(duration, 2), "status": status,
            "truncated": self.truncated, "messages_processed": self.messages,
            "prefixes": [{
                "prefix": str(net),
                "announcements": self.counts[str(net)]["announcements"],
                "withdrawals": self.counts[str(net)]["withdrawals"],
                "unique_ripe_collectors": len(self.counts[str(net)]["collectors"]),
                "origin_asns": dict(self.counts[str(net)]["origins"].most_common(15)),
            } for net in self.monitors],
            "interpretation_ceiling": (
                "Scoped BGP UPDATE count during observed connection time. "
                "Not a continuous global history, a routing-hijack diagnosis, "
                "or evidence of military/cyber attribution."),
        }


def sample(prefixes, state, duration=120, continuous=False, flush_seconds=300):
    try:
        import websocket
    except ImportError as exc:
        raise SystemExit("Install requirements-friction-live.txt to use RIPE RIS Live") from exc
    nets = allowed_prefixes(prefixes)
    if not continuous and not 10 <= duration <= 3600:
        raise ValueError("Bounded sample duration must be 10-3600 seconds")
    state = Path(state)
    stop_at = float("inf") if continuous else time.monotonic() + duration
    window = Window([str(x) for x in nets])
    connection = None
    connected = False
    last_flush = time.monotonic()

    def flush(now=None, status=None):
        nonlocal window, last_flush
        now = now or utcnow()
        label = status or ("collected" if connected else "unavailable")
        output = window.output(now, label)
        write_json(state / "latest" / "ris_sampling.json", output)
        write_json(state / "history" / "ris_sampling" /
                   (now.strftime("%Y%m%dT%H%M%SZ") + ".json"), output)
        window = Window([str(x) for x in nets], started=now)
        last_flush = time.monotonic()

    backoff = 2
    try:
        while time.monotonic() < stop_at:
            try:
                connection = websocket.create_connection(ENDPOINT, timeout=15)
                connected = True
                backoff = 2
                for prefix in nets:
                    connection.send(json.dumps({"type": "ris_subscribe", "data": {
                        "prefix": str(prefix), "type": "UPDATE",
                        "moreSpecific": True, "lessSpecific": False,
                        "socketOptions": {"includeRaw": False},
                    }}))
                while time.monotonic() < stop_at:
                    try:
                        raw = connection.recv()
                        if raw:
                            window.accept(json.loads(raw))
                    except websocket.WebSocketTimeoutException:
                        pass
                    if continuous and time.monotonic() - last_flush >= flush_seconds:
                        flush(status="collected")
                break
            except (OSError, ValueError, websocket.WebSocketException) as exc:
                connected = False
                if continuous:
                    flush(status="partial")
                if time.monotonic() >= stop_at:
                    break
                time.sleep(min(backoff, max(0.0, stop_at - time.monotonic())))
                backoff = min(backoff * 2, 60)
            finally:
                if connection is not None:
                    connection.close()
                    connection = None
    finally:
        flush(status="collected" if connected else "partial")
    return connected


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", action="append", required=True,
                   help="Explicit globally routable BGP prefix; repeat up to 8 times")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--continuous", action="store_true")
    args = p.parse_args()
    success = sample(args.prefix, args.state, args.duration, args.continuous)
    print("RIPE RIS sample completed" if success else "RIPE RIS sample incomplete; see health JSON")
    return 0 if success else 1

if __name__ == "__main__":
    raise SystemExit(main())
