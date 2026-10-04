import argparse
import json
import os
import subprocess
import sqlite3
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from dotenv import load_dotenv
from .config import Settings
from .database import Database
from .library import Library
from .auth import Auth


def main():
    parser=argparse.ArgumentParser(description='mvideo library service and explicit maintenance commands')
    parser.add_argument('--env',help='Explicit local provider/configuration .env; never logged')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('scan'); sub.add_parser('pair'); sub.add_parser('revoke-all')
    sub.add_parser('report')
    filenames=sub.add_parser('fix-filenames',help='Preview the reviewed filename repair plan; use --apply to rename and migrate catalog references')
    filenames.add_argument('--apply',action='store_true')
    filenames.add_argument('--plan',type=Path,help='Explicit reviewed JSON plan; defaults to the bundled library repair plan')
    loudness=sub.add_parser('measure-loudness',help='Measure catalog audio without changing media; resumes automatically')
    loudness.add_argument('--force',action='store_true',help='Remeasure unchanged videos too')
    loudness.add_argument('--limit',type=int,help='Process at most N uncached videos in this run')
    loudness.add_argument('--timeout',type=int,default=1800,help='Maximum analysis seconds per video (default: 1800)')
    loudness.add_argument('--status',action='store_true',help='Report saved measurement coverage without scanning')
    starters=sub.add_parser('seed-playlists',help='Resolve curated starter mixes against the catalog')
    starters.add_argument('--apply',action='store_true',help='Save once; otherwise preview matched and missing songs')
    identity=sub.add_parser('identity'); identity.add_argument('artist'); identity.add_argument('mbid')
    override=sub.add_parser('override'); override.add_argument('id'); override.add_argument('--artist'); override.add_argument('--title',required=True); override.add_argument('--year',type=int)
    serve=sub.add_parser('serve'); serve.add_argument('--host',default='127.0.0.1'); serve.add_argument('--port',type=int,default=8765)
    serve.add_argument('--scan-interval',type=int,default=1800,help='Scan at startup and every N seconds (0 disables startup/periodic scans)')
    serve.add_argument('--watch-mode',choices=['polling','native','off'],help='Filesystem watcher (default: MVIDEO_WATCH_MODE or polling)')
    args=parser.parse_args()
    if args.command=='measure-loudness' and ((args.limit is not None and args.limit < 1) or args.timeout < 1):
        parser.error('Loudness limit and timeout must be positive')
    if args.command=='serve' and args.scan_interval != 0 and args.scan_interval < 60:
        parser.error('Scan interval must be at least 60 seconds, or 0 to disable')
    if args.env:load_dotenv(args.env,override=False)
    settings=Settings.from_env()
    if args.command=='serve' and args.watch_mode:
        settings=replace(settings,watch_mode=args.watch_mode)
    settings.prepare()
    database=Database(settings.state/'library.sqlite3')
    if args.command=='serve':
        import uvicorn
        from .api import create_app
        app=create_app(settings,scan_interval=args.scan_interval)
        uvicorn.run(app,host=args.host,port=args.port,access_log=False,log_level='warning')
    elif args.command=='scan':print(json.dumps(Library(settings,database).scan()))
    elif args.command=='fix-filenames':
        from .filenames import FilenameRepair, load_plan
        try:
            repair=FilenameRepair(settings,database)
            plan=load_plan(args.plan)
            result=repair.apply(plan,progress=lambda event: print(json.dumps(event),flush=True)) if args.apply else repair.preview(plan)
            print(json.dumps(result,indent=2))
            if result.get('conflict'): raise SystemExit(1)
        except KeyboardInterrupt:
            print('Interrupted. Rerun with --apply to recover any pending rename and continue.',file=sys.stderr)
            raise SystemExit(130)
        except (OSError,ValueError,RuntimeError,sqlite3.Error) as error:
            print('Filename repair stopped: '+str(error),file=sys.stderr)
            raise SystemExit(1)
    elif args.command=='measure-loudness':
        from .loudness import LoudnessScanner
        scanner=LoudnessScanner(settings,database)
        if args.status:
            print(json.dumps(scanner.status(),indent=2))
            return
        try:
            result=scanner.run(force=args.force,limit=args.limit,timeout=args.timeout,
                               progress=lambda event: print(json.dumps(event,allow_nan=False),flush=True))
        except KeyboardInterrupt:
            print('Interrupted. Completed measurements are saved; rerun the same command to resume.',file=sys.stderr)
            raise SystemExit(130)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            print('Loudness scan could not start: '+str(error),file=sys.stderr)
            raise SystemExit(1)
        print(json.dumps(result,indent=2,allow_nan=False))
        if result['error'] or result['deferred']: raise SystemExit(1)
    elif args.command=='seed-playlists':
        from .playlists import starter_playlists
        print(json.dumps(starter_playlists(database,apply=args.apply),indent=2,ensure_ascii=False))
    elif args.command=='pair':print('One-time code (5 minutes, 5 attempts): '+Auth(database).pair_code())
    elif args.command=='revoke-all':
        with database.connect() as db:db.execute('DELETE FROM sessions')
        print('All mvideo sessions revoked')
    elif args.command=='identity':
        mbid=str(uuid.UUID(args.mbid))
        with database.connect() as db:
            db.execute('INSERT OR REPLACE INTO identities VALUES(?,?)',(args.artist,mbid))
            db.execute('DELETE FROM metadata WHERE artist=?',(args.artist,))
        print('Artist identity saved; metadata will refresh on next visit')
    elif args.command=='override':
        if args.year is not None and not 1888<=args.year<=2100:parser.error('Year must be 1888–2100')
        with database.connect() as db:
            db.execute('INSERT OR REPLACE INTO overrides VALUES(?,?,?,?)',(args.id,args.artist,args.title,args.year))
            db.execute('UPDATE videos SET mtime=-1 WHERE id=?',(args.id,))
        print('Override saved; run scan to apply. Source media remains unchanged.')
    elif args.command=='report':
        from collections import Counter
        from .playback import playback_plan
        with database.connect() as db:
            rows=db.execute('SELECT * FROM videos WHERE available=1').fetchall()
        print(json.dumps({'total':len(rows),'extensions':dict(Counter(Path(r['path']).suffix.lower() for r in rows)),
                          'playback':dict(Counter(playback_plan(json.loads(r['probe'] or '{}')) for r in rows)),
                          'needs_review':sum(bool(json.loads(r['warnings'])) for r in rows)},indent=2))


if __name__=='__main__':main()
