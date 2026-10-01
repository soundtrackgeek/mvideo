import argparse
import json
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from .config import Settings
from .database import Database
from .library import Library
from .auth import Auth


def main():
    parser=argparse.ArgumentParser(description='mvideo read-only library service')
    parser.add_argument('--env',help='Explicit local provider/configuration .env; never logged')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('scan'); sub.add_parser('pair'); sub.add_parser('revoke-all')
    sub.add_parser('report')
    identity=sub.add_parser('identity'); identity.add_argument('artist'); identity.add_argument('mbid')
    override=sub.add_parser('override'); override.add_argument('id'); override.add_argument('--artist'); override.add_argument('--title',required=True); override.add_argument('--year',type=int)
    serve=sub.add_parser('serve'); serve.add_argument('--host',default='127.0.0.1'); serve.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if args.env:load_dotenv(args.env,override=False)
    settings=Settings.from_env(); settings.prepare()
    database=Database(settings.state/'library.sqlite3')
    if args.command=='serve':
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(settings),host=args.host,port=args.port,access_log=False,log_level='warning')
    elif args.command=='scan':print(json.dumps(Library(settings,database).scan()))
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
