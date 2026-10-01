import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from mvideo.api import create_app
from mvideo.config import Settings
from mvideo.parsing import parse_filename
from mvideo.playback import make_queue,playback_plan

PROBE={'format':{'format_name':'mov,mp4,m4a,3gp,3g2,mj2','duration':'10'},'streams':[
 {'codec_type':'video','codec_name':'h264','profile':'High','level':41,'pix_fmt':'yuv420p','width':1280,'height':720,'r_frame_rate':'30/1','field_order':'progressive'},
 {'codec_type':'audio','codec_name':'aac','profile':'LC','channels':2,'sample_rate':'48000'}]}

@pytest.fixture
def service(tmp_path):
    root=tmp_path/'media';root.mkdir()
    app=create_app(Settings(root,tmp_path/'state'))
    app.state.library.probe=lambda path: PROBE
    yield app,TestClient(app),root
    app.state.playback.close()
    app.state.metadata.close()


def login(app,client):
    response=client.post('/api/pair',json={'code':app.state.auth.pair_code()})
    return {'Authorization':'Bearer '+response.json()['token']}


def test_background_artist_lookup_is_library_only_and_signs_images(service):
    app,client,root=service
    (root/'Band - Song (2000).mp4').write_bytes(b'x')
    app.state.library.scan()
    headers=login(app,client)
    calls=[]
    def lookup(name):
        calls.append(name)
        return {'state':'available','images':['https://assets.fanart.tv/band.jpg'],'pending':False}
    app.state.metadata.lookup=lookup
    assert client.get('/api/artist?name=Band&background=true').status_code==401
    assert client.get('/api/artist?name=Outside&background=true',headers=headers).status_code==404
    assert calls==[]
    data=client.get('/api/artist?name=BAND&background=true',headers=headers).json()
    assert calls==['Band'] and data['pending'] is False
    assert data['images'][0].startswith('/artwork/')
    assert 'assets.fanart.tv' not in data['images'][0]
    client.delete('/api/session',headers=headers)
    assert client.get(data['images'][0]).status_code==401


def test_facet_artwork_is_scoped_cached_and_authorized(service):
    app,client,root=service
    for name in ('Band - Early (1962)', 'BAND - Later (1997)', 'Other - Song (1985)', 'Other - Unknown'):
        (root/(name+'.mp4')).write_bytes(b'x')
    app.state.library.scan()
    headers=login(app,client)
    def no_provider(*args, **kwargs):
        pytest.fail('Facet browsing must not call metadata providers')
    app.state.metadata.artist=no_provider
    with app.state.database.connect() as db:
        db.execute('INSERT INTO identities VALUES(?,?)',('band','verified-id'))
        db.execute('INSERT INTO metadata VALUES(?,?,?)',('band',json.dumps({'images':['https://assets.fanart.tv/band.jpg'],'mbid':'verified-id'}),9999999999))
        # Cached but unverified provider data must never win over a local still.
        db.execute('INSERT INTO metadata VALUES(?,?,?)',('Other',json.dumps({'images':['https://assets.fanart.tv/wrong.jpg']}),9999999999))
    assert client.get('/api/facets/artists').status_code==401
    images=[]
    for kind in ('artists','years','decades'):
        response=client.get('/api/facets/'+kind,headers=headers).json()
        for item in response['items']:
            assert 'representative_id' not in item
            identity=item['thumbnail'].split('/')[2]
            source=app.state.library.get(identity)
            if kind=='artists':
                assert source['artist'].casefold()==item['name'].casefold()
                if item['name'].casefold()=='band':
                    assert item['image'].startswith('/artwork/')
                    assert item['image_attribution']=='fanart.tv'
                else: assert item['image']==item['thumbnail']
            elif kind=='years': assert source['year']==item['name']
            else: assert source['year']//10*10==item['name']
            images.extend([item['image'],item['thumbnail']])
        paged=client.get('/api/facets/'+kind+'?limit=1&offset=1',headers=headers).json()
        assert paged['items'][0]['name']==response['items'][1]['name']
    filtered=client.get('/api/facets/artists?q=Later',headers=headers).json()['items'][0]
    assert app.state.library.get(filtered['thumbnail'].split('/')[2])['year']==1997
    client.delete('/api/session',headers=headers)
    for image in images: assert client.get(image).status_code==401


def test_featured_artwork_is_verified_library_only_and_scoped(service):
    app,client,root=service
    (root/'Library Artist - Song (2000).mp4').write_bytes(b'x')
    app.state.library.scan()
    headers=login(app,client)
    assert client.get('/api/featured').status_code==401
    assert client.get('/api/featured',headers=headers).json()=={'item':None}
    data={'images':['https://assets.fanart.tv/one.jpg','https://assets.fanart.tv/two.jpg'],
          'background_count':2,'image_source_url':'https://fanart.tv/artist/example/', 'mbid':'7364dea6-ca9a-48e3-be01-b44ad0d19897'}
    with app.state.database.connect() as db:
        for name in ('Library Artist','Outside Library'):
            db.execute('INSERT INTO identities VALUES(?,?)',(name,'7364dea6-ca9a-48e3-be01-b44ad0d19897'))
            db.execute('INSERT INTO metadata VALUES(?,?,?)',(name,json.dumps(data),9999999999))
    images=set()
    for _ in range(24):
        result=client.get('/api/featured',headers=headers).json()['item']
        assert result['artist']=='Library Artist'
        assert result['image'].startswith('/artwork/') and 'assets.fanart.tv' not in result['image']
        images.add(result['image'].split('/')[3])
    assert images=={'0','1'}
    client.delete('/api/session',headers=headers)
    assert client.get(result['image']).status_code==401

@pytest.mark.parametrize('name,artist,title,year,warning',[
 ('a-ha - Take On Me (1985).mp4','a-ha','Take On Me',1985,None),
 ('AC-DC - Rock & Roll! (1979).mkv','AC-DC','Rock & Roll!',1979,None),
 ('Björk - Jóga (1997).mp4','Björk','Jóga',1997,None),
 ('Band - Song - Live (2001).mp4',None,'Band - Song - Live',2001,'ambiguous_separator'),
 ('Prince - 1999.mp4','Prince','1999',None,'missing_year'),
 ('Artist - Song (1985) (2020).mp4','Artist','Song (1985) (2020)',None,'ambiguous_year'),
 ('Unlabelled.mp4',None,'Unlabelled',None,'missing_artist'),
 ('Artist - Song (1234).mp4','Artist','Song (1234)',None,'ambiguous_year')])
def test_parser(name,artist,title,year,warning):
    value=parse_filename(name)
    assert (value['artist'],value['title'],value['year'])==(artist,title,year)
    assert warning in value['warnings'] if warning else not value['warnings']


def test_scan_search_incremental_and_offline(service):
    app,client,root=service;lib=app.state.library
    p=root/'a-ha - Take On Me (1985).mp4';p.write_bytes(b'0123456789')
    (root/'Björk - Jóga (1997).mkv').write_bytes(b'x')
    assert lib.scan()['changed']==2
    assert lib.scan()['changed']==0
    assert lib.videos(q='a-ha')['total']==1
    assert lib.videos(q='bjork')['total']==1
    assert lib.videos(q='1985',field='year')['total']==1
    assert lib.videos(artist='a-ha',decade=1990)['total']==0
    assert lib.videos(q='" OR *')['total']==0
    assert [(item['name'],item['count']) for item in lib.facets('decades')['items']]==[(1980,1),(1990,1)]
    (root/'A-HA - Another Song (2000).mp4').write_bytes(b'x')
    lib.scan()
    assert lib.videos(artist='A-Ha')['total']==2
    assert lib.facets('artists')['total']==2
    (root/'A-HA - Another Song (2000).mp4').unlink()
    lib.scan()
    p.write_bytes(b'changed');assert lib.scan()['changed']==1
    p.unlink();assert lib.scan()['missing']==1
    root.rename(root.with_name('offline'))
    assert lib.scan()['state']=='error'
    assert lib.videos()['total']==1


def test_revision_and_ranges_and_auth(service):
    app,client,root=service
    path=root/'Band - Song (2000).mp4';path.write_bytes(b'0123456789')
    app.state.library.scan()
    assert client.get('/api/videos').status_code==401
    headers=login(app,client)
    page=client.get('/api/videos',headers=headers).json();identity=page['items'][0]['id']
    assert client.get('/api/videos?revision=-1',headers=headers).status_code==409
    assert client.post('/api/queue',json={'artist':'Other','start':identity},headers=headers).status_code==409
    result=client.post('/api/playback/'+identity,headers=headers).json()
    assert result['state']=='ready'
    response=client.get(result['url'],headers={'Range':'bytes=3-6'})
    assert response.status_code==206 and response.content==b'3456'
    assert client.get(result['url'],headers={'Range':'bytes=-3'}).content==b'789'
    assert client.get(result['url'],headers={'Range':'bytes=99-100'}).status_code==416
    assert client.head(result['url']).headers['content-length']=='10'
    assert str(root) not in json.dumps(page)
    client.delete('/api/session',headers=headers)
    assert client.get(result['url']).status_code==401


def test_pair_one_time_and_lockout(service):
    app,client,_=service;code=app.state.auth.pair_code()
    for _ in range(5):assert client.post('/api/pair',json={'code':'x'*8}).status_code==422
    assert client.post('/api/pair',json={'code':code}).status_code==200
    assert client.post('/api/pair',json={'code':code}).status_code==401
    code=app.state.auth.pair_code()
    wrong='00000000' if code!='00000000' else '11111111'
    for _ in range(5):client.post('/api/pair',json={'code':wrong})
    assert client.post('/api/pair',json={'code':code}).status_code==401


def test_queue_complete_selection_no_repeats():
    ids=[str(n) for n in range(15001)]
    for _ in range(4):
        q=make_queue(ids,shuffle=True,start='8000')
        assert q[0]=='8000' and len(q)==len(set(q))==15001 and set(q)==set(ids)
    assert make_queue(['a','b','c'],start='b')==['b','c','a']
    assert make_queue([])==[]


def test_codec_policy():
    p=json.loads(json.dumps(PROBE));assert playback_plan(p)=='direct'
    p['format']['format_name']='matroska,webm';assert playback_plan(p)=='remux'
    p['streams'][1]['codec_name']='mp3';assert playback_plan(p)=='audio_transcode'
    p['streams'][0]['codec_name']='mpeg2video';assert playback_plan(p)=='transcode'
    p['streams'][0]['color_transfer']='smpte2084';assert playback_plan(p)=='unsupported_hdr'
    assert playback_plan({})=='unsupported'
    p=json.loads(json.dumps(PROBE));p['streams'][0]['field_order']='tt';assert playback_plan(p)=='transcode'


def test_pagination_15000(service):
    app,_,_=service
    with app.state.database.connect() as db:
        for n in range(15000):
            data={'artist':f'Artist {n%300}','title':f'Song {n:05d}','year':1950+n%76}
            db.execute('INSERT INTO videos VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(str(n),str(n)+'.mp4',1,1,data['artist'],data['title'],data['year'],str(n),'[]',json.dumps(PROBE),None,1))
            app.state.library._index(db,str(n),data)
    seen=[]
    for offset in range(0,15000,100):
        page=app.state.library.videos(limit=100,offset=offset)
        assert page['total']==15000
        seen += [r['id'] for r in page['items']]
    assert len(set(seen))==15000
    assert app.state.library.videos(q='Song 14999')['total']==1


def test_path_escape_refused(service):
    app,_,root=service;lib=app.state.library
    path=root/'Band - Song.mp4';path.write_bytes(b'x');lib.scan();identity=lib.ids()[0]
    with app.state.database.connect() as db:db.execute('UPDATE videos SET path=? WHERE id=?',('../outside.mp4',identity))
    (root.parent/'outside.mp4').write_bytes(b'x')
    with pytest.raises(FileNotFoundError):lib.source(identity)


def test_state_cannot_be_in_library(tmp_path):
    with pytest.raises(ValueError):Settings(tmp_path,tmp_path/'cache').prepare()
