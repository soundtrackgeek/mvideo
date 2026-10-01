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


def login(app,client):
    response=client.post('/api/pair',json={'code':app.state.auth.pair_code()})
    return {'Authorization':'Bearer '+response.json()['token']}

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
    assert lib.facets('decades')['items']==[{'name':1980,'count':1},{'name':1990,'count':1}]
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
