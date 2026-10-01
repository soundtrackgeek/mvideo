"""Lazy server-only providers. A name is never treated as a verified artist identity."""
import html
import json
import os
import re
import threading
import time
import uuid
from urllib.parse import urlparse
import httpx


class Metadata:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings
        self.lock = threading.Lock()
        self.last_request = 0.0
        self.backoff_until = 0.0

    def request(self, url, params=None, headers=None):
        # Caller holds the provider lock: at most one request/second across providers.
        if time.time() < self.backoff_until:
            raise ValueError('Provider temporarily unavailable')
        time.sleep(max(0,1-(time.monotonic()-self.last_request)))
        self.last_request = time.monotonic()
        with httpx.Client(timeout=15,follow_redirects=False) as client:
            response = client.get(url,params=params,headers=headers)
            if response.status_code==429:
                self.backoff_until=time.time()+300
                raise ValueError('Provider rate limit')
            response.raise_for_status()
            data=response.json()
            if data.get('error'):
                self.backoff_until=time.time()+300
                raise ValueError('Provider unavailable')
            return data

    def artist(self, name):
        with self.lock:
            with self.db.connect() as db:
                cached=db.execute('SELECT * FROM metadata WHERE artist=?',(name,)).fetchone()
                identity=db.execute('SELECT mbid FROM identities WHERE artist=?',(name,)).fetchone()
            if cached and cached['expires']>time.time():
                return json.loads(cached['data'])
            data={'state':'unavailable','biography':None,'source_url':None,'images':[], 'mbid':identity[0] if identity else None}
            key=os.environ.get('LAST_FM')
            try:
                if key:
                    params={'method':'artist.getinfo','api_key':key,'format':'json','autocorrect':'0'}
                    params.update({'mbid':identity[0]} if identity else {'artist':name})
                    result=self.request('https://ws.audioscrobbler.com/2.0/',params)['artist']
                    mbid=result.get('mbid','')
                    if not identity:
                        data.update(state='needs_identity',candidate_mbid=mbid or None,
                                    candidate_name=result.get('name'))
                    elif mbid and mbid.lower()!=identity[0].lower():
                        data['state']='identity_mismatch'
                    else:
                        text=html.unescape(re.sub('<[^>]+>','',result.get('bio',{}).get('summary',''))).strip()
                        source=result.get('url','').replace('http://','https://',1)
                        if urlparse(source).hostname not in ('www.last.fm','last.fm'):
                            source='https://www.last.fm/'
                        data.update(state='available',biography=text or None,source_url=source, attribution='Biography · Last.fm')
                if identity and os.environ.get('FANART_TV'):
                    # v3 remains supported and works with a project key; personal client key is optional.
                    result=self.request('https://webservice.fanart.tv/v3/music/'+str(uuid.UUID(identity[0])),
                        {'api_key':os.environ['FANART_TV']})
                    images=result.get('artistbackground',[])[:4]+result.get('artistthumb',[])[:1]
                    for item in images:
                        url=item.get('url','').replace('http://','https://',1)
                        if urlparse(url).hostname=='assets.fanart.tv' and urlparse(url).scheme=='https':
                            data['images'].append(url)
                    data['image_attribution']='Artist images · fanart.tv'
                    data['image_source_url']='https://fanart.tv/artist/'+identity[0]+'/'
            except (httpx.HTTPError,ValueError,KeyError,TypeError):
                if cached:
                    data=json.loads(cached['data']); data['stale']=True
                else:
                    data['state']='unavailable'
            ttl=86400 if data['state']=='available' else 900
            with self.db.connect() as db:
                db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?,?)',(name,json.dumps(data),int(time.time())+ttl))
            return data

    def image(self, name, index):
        import hashlib
        data=self.artist(name)
        try:
            url=data['images'][index]
        except IndexError:
            raise FileNotFoundError('Artist image unavailable')
        target=self.settings.state/'artwork'/(hashlib.sha256(url.encode()).hexdigest()+'.jpg')
        if not target.exists():
            with self.lock, httpx.Client(timeout=20,follow_redirects=False) as client:
                with client.stream('GET',url) as response:
                    response.raise_for_status()
                    if not response.headers.get('content-type','').startswith('image/'):
                        raise FileNotFoundError('Invalid artwork response')
                    chunks=[]; size=0
                    for chunk in response.iter_bytes():
                        size+=len(chunk)
                        if size>10*1024**2:
                            raise FileNotFoundError('Artwork too large')
                        chunks.append(chunk)
                temp=target.with_suffix('.partial')
                temp.write_bytes(b''.join(chunks)); temp.replace(target)
        return target
