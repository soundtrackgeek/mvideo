"""Lazy, cached server-only providers with recording-backed artist matching."""
import html
import json
import os
import re
import random
import threading
import time
import uuid
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import httpx
from .artist_match import match_artist


class Metadata:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings
        self.lock = threading.Lock()
        self.last_request = 0.0
        self.backoff_until = {}
        self.jobs_lock = threading.Lock()
        self.pending = set()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mvideo-artwork')
        self.image_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='mvideo-artwork-image')
        self.image_lock = threading.Lock()

    def close(self):
        self.image_pool.shutdown(wait=True, cancel_futures=True)
        self.pool.shutdown(wait=True, cancel_futures=True)

    def cached(self, name):
        with self.db.connect() as db:
            cached = db.execute('SELECT * FROM metadata WHERE artist=? COLLATE NOCASE', (name,)).fetchone()
            identity = db.execute('SELECT mbid FROM identities WHERE artist=? COLLATE NOCASE', (name,)).fetchone()
        data = json.loads(cached['data']) if cached else None
        if data and identity and data.get('mbid') != identity['mbid']:
            return None, None, identity
        if data and data.get('images') and not identity and data.get('identity_source') != 'musicbrainz_recording':
            return None, None, identity
        return data, cached['expires'] if cached else None, identity

    @staticmethod
    def fresh(data, expires):
        # Revisit old negative cache entries created by the manual-only resolver.
        return bool(data and expires > time.time() and (data.get('images') or data.get('match_version') == 1))

    def lookup(self, name):
        """Return immediately; one bounded worker resolves missing artwork."""
        data, expires, _ = self.cached(name)
        if self.fresh(data, expires):
            return data | {'pending': False}
        key = name.casefold()
        with self.jobs_lock:
            if key not in self.pending and len(self.pending) < 64:
                self.pending.add(key)
                self.pool.submit(self._load, name, key)
        return (data or {'state': 'loading', 'images': [], 'biography': None}) | {'pending': True}

    def _load(self, name, key):
        try:
            self.artist(name)
        finally:
            with self.jobs_lock:
                self.pending.discard(key)

    def request(self, url, params=None, headers=None):
        # Caller holds the provider lock: at most one request/second across providers.
        provider = urlparse(url).hostname
        if time.time() < self.backoff_until.get(provider, 0):
            raise ValueError('Provider temporarily unavailable')
        time.sleep(max(0,1-(time.monotonic()-self.last_request)))
        self.last_request = time.monotonic()
        with httpx.Client(timeout=15,follow_redirects=False) as client:
            response = client.get(url,params=params,headers=headers or {
                'User-Agent': 'mvideo/0.4.1 (https://github.com/soundtrackgeek/mvideo)'})
            if response.status_code in (429, 503):
                self.backoff_until[provider]=time.time()+300
                raise ValueError('Provider rate limit')
            response.raise_for_status()
            data=response.json()
            if data.get('error'):
                if data['error'] in (11, 16, 29):
                    self.backoff_until[provider]=time.time()+300
                raise ValueError('Provider unavailable')
            return data

    def artist(self, name):
        with self.lock:
            previous, expires, identity = self.cached(name)
            if self.fresh(previous, expires):
                return previous
            cached = {'data': json.dumps(previous)} if previous else None
            evidence = []
            resolution_failed = False
            if not identity and (os.environ.get('FANART_TV') or os.environ.get('LAST_FM')):
                if previous and previous.get('identity_source') == 'musicbrainz_recording' and previous.get('mbid'):
                    identity = (previous['mbid'],)
                    evidence = previous.get('matched_tracks', [])
                else:
                    with self.db.connect() as db:
                        tracks = db.execute('''SELECT title FROM videos WHERE artist=? COLLATE NOCASE AND available=1
                            GROUP BY title COLLATE NOCASE ORDER BY length(title) DESC, title LIMIT 3''', (name,)).fetchall()
                    try:
                        mbid, evidence = match_artist(name, [r['title'] for r in tracks], self.request)
                        if mbid: identity = (mbid,)
                    except (httpx.HTTPError, ValueError, KeyError, TypeError):
                        resolution_failed = True
            data={'state':'unavailable','biography':None,'source_url':None,'images':[], 'mbid':identity[0] if identity else None}
            data['match_version'] = 1
            if evidence:
                data.update(identity_source='musicbrainz_recording', matched_tracks=evidence)
            key=os.environ.get('LAST_FM')
            provider_failed = False
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
                        # Some Last.fm MBID pages have only a link while the canonical ASCII-name page has the bio.
                        # Only allow this fallback for a matched identity and an equivalent punctuation-normalized name.
                        def normalized(value):
                            return ''.join(c for c in unicodedata.normalize('NFKD',value).casefold() if c.isalnum())
                        if len(text) < 50 and normalized(result.get('name','')) == normalized(name):
                            fallback=self.request('https://ws.audioscrobbler.com/2.0/',
                                {'method':'artist.getinfo','api_key':key,'format':'json','autocorrect':'0','artist':name}).get('artist',{})
                            if normalized(fallback.get('name','')) == normalized(name) and (not fallback.get('mbid') or fallback['mbid']==identity[0]):
                                text=html.unescape(re.sub('<[^>]+>','',fallback.get('bio',{}).get('summary',''))).strip()
                                source=fallback.get('url',source).replace('http://','https://',1)
                        text=re.sub(r'\s*Read more on Last.fm\.?\s*$', '', text).strip()
                        if urlparse(source).hostname not in ('www.last.fm','last.fm'):
                            source='https://www.last.fm/'
                        data.update(state='available',biography=text or None,source_url=source, attribution='Biography · Last.fm')
            except (httpx.HTTPError,ValueError,KeyError,TypeError):
                provider_failed = True
                if cached:
                    old = json.loads(cached['data'])
                    for field in ('biography', 'source_url', 'attribution'):
                        if old.get(field): data[field] = old[field]
                    data['stale']=True
            try:
                if identity and os.environ.get('FANART_TV'):
                    # v3 remains supported and works with a project key; personal client key is optional.
                    result=self.request('https://webservice.fanart.tv/v3/music/'+str(uuid.UUID(identity[0])),
                        {'api_key':os.environ['FANART_TV']})
                    backgrounds=result.get('artistbackground',[])[:12]
                    images=backgrounds+result.get('artistthumb',[])[:1]
                    data['images']=[]
                    data['background_count']=0
                    for item in images:
                        url=item.get('url','').replace('http://','https://',1)
                        if urlparse(url).hostname=='assets.fanart.tv' and urlparse(url).scheme=='https':
                            data['images'].append(url)
                            if item in backgrounds: data['background_count']+=1
                    data['image_attribution']='Artist images · fanart.tv'
                    data['image_source_url']='https://fanart.tv/artist/'+identity[0]+'/'
            except (httpx.HTTPError,ValueError,KeyError,TypeError) as error:
                provider_failed |= not (isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 404)
                if cached:
                    old = json.loads(cached['data'])
                    for field in ('images', 'background_count', 'image_attribution', 'image_source_url'):
                        if old.get(field): data[field] = old[field]
                    data['stale']=True
            ttl=900 if resolution_failed or provider_failed or data.get('stale') else 86400
            if data['images']: data['state']='available'
            with self.db.connect() as db:
                db.execute('DELETE FROM metadata WHERE artist=? COLLATE NOCASE', (name,))
                db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?,?)',(name,json.dumps(data),int(time.time())+ttl))
            return data

    def cached_artwork(self, names):
        # Grid responses stay cheap. Visible tiles request lazy matching separately.
        if not names: return set()
        with self.db.connect() as db:
            rows=db.execute(f'''SELECT m.artist, m.data, i.mbid FROM metadata m
                LEFT JOIN identities i ON i.artist=m.artist COLLATE NOCASE
                WHERE m.artist COLLATE NOCASE IN ({','.join('?' for _ in names)})''', names).fetchall()
        return {row['artist'].casefold() for row in rows
                if (data := json.loads(row['data'])).get('images') and
                ((row['mbid'] and data.get('mbid') == row['mbid']) or
                 (not row['mbid'] and data.get('identity_source') == 'musicbrainz_recording' and data.get('mbid')))}

    def featured(self):
        # Equal artist weighting, limited to verified identities that still have available videos.
        # Never crawl the entire library during an app launch.
        with self.db.connect() as db:
            rows=db.execute('''SELECT m.artist, m.data, i.mbid FROM metadata m
                LEFT JOIN identities i ON m.artist=i.artist COLLATE NOCASE
                WHERE EXISTS (SELECT 1 FROM videos v WHERE v.artist=m.artist COLLATE NOCASE AND v.available=1)''').fetchall()
        candidates=[]
        for row in rows:
            data=json.loads(row['data']) if row['data'] else {}
            matched = (row['mbid'] and data.get('mbid') == row['mbid']) or (not row['mbid'] and data.get('identity_source') == 'musicbrainz_recording' and data.get('mbid'))
            if matched and data.get('background_count',0)>0:
                candidates.append((row['artist'],data))
        if not candidates: return None
        name,data=random.choice(candidates)
        return {'artist':name,'index':random.randrange(data['background_count']),
                'attribution':'Artist photography · fanart.tv','source_url':data['image_source_url']}

    def image(self, name, index):
        import hashlib
        data, _, _ = self.cached(name)
        if not data or not data.get('images'): data=self.artist(name)
        try:
            url=data['images'][index]
        except IndexError:
            raise FileNotFoundError('Artist image unavailable')
        target=self.settings.state/'artwork'/(hashlib.sha256(url.encode()).hexdigest()+'.jpg')
        if not target.exists():
            with self.image_lock, httpx.Client(timeout=20,follow_redirects=False) as client:
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
