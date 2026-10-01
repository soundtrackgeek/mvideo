from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field
import threading
import subprocess
from .auth import Auth
from .config import Settings
from .database import Database
from .library import Library
from .metadata import Metadata
from .playback import Playback, make_queue
from .playlists import Playlists, PlaylistConflict


class PairRequest(BaseModel):
    code: str = Field(min_length=8,max_length=8,pattern=r'^\d+$')


class Scope(BaseModel):
    q: str = Field(default='',max_length=256)
    artist: str | None = Field(default=None,max_length=512)
    year: int | None = Field(default=None,ge=1888,le=2100)
    decade: int | None = Field(default=None,ge=1880,le=2100)
    unknown: bool = False
    field: Literal['all','artist','title','year'] = 'all'
    playlist: str | None = Field(default=None,max_length=64)


class PlaylistWrite(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    description: str = Field(default='',max_length=2000)
    ids: list[str] = Field(default_factory=list,max_length=5000)


class PlaylistUpdate(PlaylistWrite):
    version: int = Field(ge=1)


class QueueRequest(Scope):
    shuffle: bool = False
    start: str | None = None


def create_app(settings=None):
    settings=settings or Settings.from_env()
    settings.prepare()
    database=Database(settings.state/'library.sqlite3')
    library=Library(settings,database)
    auth=Auth(database)
    playback=Playback(settings,library)
    metadata=Metadata(database,settings)
    playlists=Playlists(database)
    @asynccontextmanager
    async def lifespan(app):
        yield
        playback.close()
        metadata.close()
    app=FastAPI(title='mvideo',version='0.8.0',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.library=library; app.state.auth=auth; app.state.playback=playback
    app.state.metadata=metadata; app.state.database=database
    app.state.playlists=playlists

    @app.middleware('http')
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        if request.url.path == '/' or request.url.path.startswith('/studio'):
            response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    def session(authorization: str = Header(default='')):
        if not authorization.startswith('Bearer '):
            raise HTTPException(401,'Pair this device with the server')
        value=auth.authenticate(authorization[7:])
        if not value:
            raise HTTPException(401,'Session expired; pair again')
        return value

    def video(identity):
        try:return library.get(identity)
        except FileNotFoundError:raise HTTPException(404,'Video is no longer available')

    def public(row, sid):
        data=library.public(row)
        data['thumbnail']='/image/'+row['id']+'/'+auth.ticket(sid,'image:'+row['id'])
        return data

    @app.get('/health')
    def health(): return {'service':'mvideo','version':'0.8.0'}

    def playlist_result(value, sid):
        data = value.copy()
        cover = data.pop('cover_id', None)
        data['thumbnail'] = '/image/'+cover+'/'+auth.ticket(sid,'image:'+cover) if cover else None
        if 'items' in data:
            data['items'] = [public(r,sid) | {'available':bool(r['available'])} for r in data['items']]
        return data

    def playlist_call(action):
        try: return action()
        except FileNotFoundError as error: raise HTTPException(404,str(error))
        except PlaylistConflict as error: raise HTTPException(409,str(error))
        except ValueError as error: raise HTTPException(422,str(error))

    def check_playlist(scope):
        if scope.playlist is not None:
            with database.connect() as db:
                playlist_call(lambda: playlists.require(db,scope.playlist))

    @app.get('/api/playlists')
    def playlist_list(sid=Depends(session)):
        return {'items':[playlist_result(p,sid) for p in playlists.list()]}

    @app.post('/api/playlists',status_code=201)
    def playlist_create(body:PlaylistWrite,sid=Depends(session)):
        return playlist_result(playlist_call(lambda:playlists.save(**body.model_dump())),sid)

    @app.get('/api/playlists/{identity}')
    def playlist_detail(identity:str,sid=Depends(session)):
        return playlist_result(playlist_call(lambda:playlists.get(identity)),sid)

    @app.put('/api/playlists/{identity}')
    def playlist_update(identity:str,body:PlaylistUpdate,sid=Depends(session)):
        return playlist_result(playlist_call(lambda:playlists.save(identity=identity,**body.model_dump())),sid)

    @app.delete('/api/playlists/{identity}')
    def playlist_delete(identity:str,version:int=Query(ge=1),sid=Depends(session)):
        playlist_call(lambda:playlists.delete(identity,version))
        return {'ok':True}

    @app.post('/api/pair')
    def pair(body:PairRequest):
        token=auth.pair(body.code)
        if not token:raise HTTPException(401,'Pairing code invalid, expired or locked; create a new code on the PC')
        return {'token':token}

    @app.delete('/api/session')
    def revoke(sid=Depends(session)):
        with database.connect() as db:db.execute('DELETE FROM sessions WHERE hash=?',(sid,))
        return {'ok':True}

    @app.get('/api/status')
    def status(sid=Depends(session)):
        with database.connect() as db:
            total=db.execute('SELECT count(*) FROM videos WHERE available=1').fetchone()[0]
            unknown=db.execute('SELECT count(*) FROM videos WHERE available=1 AND year IS NULL').fetchone()[0]
        return {'total':total,'unknown_years':unknown,'revision':database.revision(),'scan':library.scan_status}

    @app.post('/api/scan')
    def scan(sid=Depends(session)):
        threading.Thread(target=library.scan,daemon=True).start()
        return {'state':'requested'}

    @app.get('/api/videos')
    def videos(scope:Scope=Depends(),limit:int=Query(48,ge=1,le=100),offset:int=Query(0,ge=0),revision:int|None=None,sid=Depends(session)):
        check_playlist(scope)
        result=library.videos(limit=limit,offset=offset,**scope.model_dump())
        if revision is not None and result['revision']!=revision:
            raise HTTPException(409,'Library changed; refresh this page')
        for item in result['items']:
            item['thumbnail']='/image/'+item['id']+'/'+auth.ticket(sid,'image:'+item['id'])
        return result

    @app.get('/api/videos/{identity}')
    def detail(identity:str,sid=Depends(session)):
        return public(video(identity),sid)

    @app.get('/api/facets/{kind}')
    def facets(kind:Literal['artists','years','decades'],q:str=Query('',max_length=256),limit:int=Query(60,ge=1,le=100),offset:int=Query(0,ge=0),sid=Depends(session)):
        result=library.facets(kind,q,limit,offset)
        artists=metadata.cached_artwork([item['name'] for item in result['items']]) if kind=='artists' else set()
        for item in result['items']:
            identity=item.pop('representative_id')
            item['thumbnail']='/image/'+identity+'/'+auth.ticket(sid,'image:'+identity)
            item['image']=item['thumbnail']
            if kind=='artists' and item['name'].casefold() in artists:
                item['image']=artwork_url(item['name'],0,sid)
                item['image_attribution']='fanart.tv'
        return result

    def artwork_url(name,index,sid):
        import hashlib
        from urllib.parse import quote
        key=hashlib.sha256(name.encode()).hexdigest()
        return f'/artwork/{key}/{index}/{auth.ticket(sid,"artwork:"+key+":"+str(index))}?name='+quote(name,safe='')

    @app.get('/api/featured')
    def featured(sid=Depends(session)):
        item=metadata.featured()
        if item:
            item['image']=artwork_url(item['artist'],item.pop('index'),sid)
        return {'item':item}

    @app.get('/api/artist')
    def artist(name:str=Query(max_length=512),background:bool=False,sid=Depends(session)):
        with database.connect() as db:
            row=db.execute('SELECT artist FROM videos WHERE artist=? COLLATE NOCASE AND available=1 LIMIT 1',(name,)).fetchone()
        if not row: raise HTTPException(404,'Artist is not in your library')
        name=row['artist']
        data=(metadata.lookup(name) if background else metadata.artist(name)).copy()
        # Never send provider credentials or provider request URLs to the client.
        data['images']=[artwork_url(name,i,sid) for i,_ in enumerate(data['images'])]
        return data

    @app.post('/api/queue')
    def queue(body:QueueRequest,sid=Depends(session)):
        check_playlist(body)
        try:ids=make_queue(library.ids(**body.model_dump(exclude={'shuffle','start'})),body.shuffle,body.start)
        except ValueError as error:raise HTTPException(409,str(error))
        return {'ids':ids,'revision':database.revision()}

    @app.post('/api/playback/{identity}')
    def prepare(identity:str,sid=Depends(session)):
        video(identity)
        try:result=playback.prepare(identity)
        except (OSError,ValueError):raise HTTPException(404,'Source file is unavailable')
        if result['state']=='ready':
            result['url']='/media/'+identity+'/'+auth.ticket(sid,'media:'+identity)+'/video.mp4'
        return result

    @app.api_route('/media/{identity}/{ticket}/video.mp4',methods=['GET','HEAD'])
    def media(identity:str,ticket:str):
        if not auth.verify_ticket(ticket,'media:'+identity):raise HTTPException(401,'Playback link expired')
        try:path=playback.path(identity)
        except (OSError,ValueError):raise HTTPException(404,'Media unavailable; retry playback')
        return FileResponse(path,media_type='video/mp4',headers={'Cache-Control':'private, no-store'})

    @app.get('/image/{identity}/{ticket}')
    def thumbnail(identity:str,ticket:str):
        if not auth.verify_ticket(ticket,'image:'+identity):raise HTTPException(401)
        try:path=playback.thumbnail(identity)
        except (OSError,ValueError,subprocess.SubprocessError):raise HTTPException(404,'Thumbnail unavailable')
        return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=3600'})

    @app.get('/artwork/{key}/{index}/{ticket}')
    def artwork(key:str,index:int,ticket:str,name:str=Query(max_length=512)):
        import hashlib
        if index<0 or hashlib.sha256(name.encode()).hexdigest()!=key or not auth.verify_ticket(ticket,'artwork:'+key+':'+str(index)):
            raise HTTPException(401)
        try:path=metadata.image(name,index)
        except Exception:raise HTTPException(404,'Artist artwork unavailable')
        return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=3600'})
    web = Path(__file__).parent/'web'
    if web.is_dir():
        @app.get('/')
        def studio_home():
            return FileResponse(web/'index.html',headers={'Cache-Control':'no-cache'})
        app.mount('/studio',StaticFiles(directory=web,html=True),name='studio')
    return app
