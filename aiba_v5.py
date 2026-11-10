#!/usr/bin/env python3
"""Build a dated AIBA dashboard; strict builds publish only complete GDELT windows."""
import argparse
import datetime as dt
import json
import shutil
import tempfile
from pathlib import Path
from aiba_v4 import download_days, build
from preconvergence import generate
from collect_wikipedia import write_outputs


def run():
    p=argparse.ArgumentParser()
    p.add_argument('--as-of', default=(dt.datetime.now(dt.timezone.utc).date()-dt.timedelta(days=1)).isoformat())
    p.add_argument('--download-days', type=int, default=0)
    p.add_argument('--wiki-days', type=int, default=0)
    p.add_argument('--strict-gdelt', action='store_true')
    p.add_argument('--allow-partial-gdelt', action='store_true', help='Publish other feeds while suppressing incomplete GDELT discovery')
    p.add_argument('--output-dir', type=Path, default=Path('_site'))
    p.add_argument('--cache-dir', type=Path, default=Path('cache'))
    args=p.parse_args(); day=dt.date.fromisoformat(args.as_of)
    if day >= dt.datetime.now(dt.timezone.utc).date():
        p.error('--as-of must be a completed UTC day')
    if args.strict_gdelt and args.allow_partial_gdelt:
        p.error('--strict-gdelt and --allow-partial-gdelt are mutually exclusive')
    if args.download_days < 0 or args.wiki_days < 0:
        p.error('collection day counts must be nonnegative')
    if args.download_days: download_days(day,args.download_days,args.cache_dir)
    attention=write_outputs(day,args.wiki_days) if args.wiki_days else None
    # Build in isolation. Failure leaves the previous output directory untouched.
    args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output_dir.parent) as tmp:
        stage=Path(tmp)
        generate(out=stage/'historical_preconvergence.json')
        outcome=build(out=stage,asof=day,cache=args.cache_dir,
                      strict=args.strict_gdelt,live_attention=attention,
                      suppress_incomplete_discovery=args.allow_partial_gdelt)
        for name in ('index.html','Global_AIBA_5_Watchboard.html'):
            (stage/name).write_bytes((stage/'Global_AIBA_4_Watchboard.html').read_bytes())
        status={'asof':day.isoformat(),'generated':outcome['generated'],
                'gdelt':outcome['data_completeness'],'discovery_status':outcome['discovery_status'],
                'wikipedia':attention or {'status':'not collected'},
                'curated_sources':'Static supplied dossiers; not reverified by automation',
                'market_series':'Static supplied historical snapshot; not live'}
        (stage/'collection_status.json').write_text(json.dumps(status,indent=2))
        (stage/'.nojekyll').touch()
        if args.output_dir.exists(): shutil.rmtree(args.output_dir)
        shutil.copytree(stage,args.output_dir)
    print(outcome['collection_summary'])
    print('Built',len(outcome['hotspots']),'candidates; algorithmic leads remain unverified.')


if __name__=='__main__': run()
