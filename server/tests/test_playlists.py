import json
import pytest
from test_service import service, login
from mvideo.database import Database
from mvideo.playlists import Playlists


def seed(service, count=4):
    app, client, root = service
    for i in range(count):
        (root / f'Band - Song {i} ({1990+i%10}).mp4').write_bytes(b'x')
    app.state.library.scan()
    return app, client, login(app, client), app.state.library.ids()


def test_playlist_atomic_order_persistence_and_conflict(service):
    app, client, headers, ids = seed(service)
    assert client.get('/api/playlists').status_code == 401
    assert client.post('/api/playlists',json={'name':'Mix'}).status_code == 401
    response = client.post('/api/playlists',headers=headers,json={'name':' My mix ', 'description':'Test', 'ids':ids[::-1]})
    assert response.status_code == 201
    playlist = response.json(); identity = playlist['id']
    assert playlist['name'] == 'My mix' and playlist['count'] == 4
    assert Playlists(Database(app.state.database.path)).get(identity)['items'][0]['id'] == ids[-1]
    read = client.get('/api/playlists/'+identity,headers=headers).json()
    assert [r['id'] for r in read['items']] == ids[::-1]
    assert all('path' not in r and r['available'] for r in read['items'])
    update = {'name':'Edited','description':'New','ids':ids[:2], 'version':1}
    assert client.put('/api/playlists/'+identity,headers=headers,json=update).status_code == 200
    assert client.put('/api/playlists/'+identity,headers=headers,json=update).status_code == 409
    assert client.delete('/api/playlists/'+identity+'?version=1',headers=headers).status_code == 409
    update['version'] = 2; update['ids'] = ['does-not-exist']
    assert client.put('/api/playlists/'+identity,headers=headers,json=update).status_code == 422
    read = client.get('/api/playlists/'+identity,headers=headers).json()
    assert read['version'] == 2 and [r['id'] for r in read['items']] == ids[:2]
    assert client.delete('/api/playlists/'+identity+'?version=2',headers=headers).status_code == 200
    assert client.get('/api/playlists/'+identity,headers=headers).status_code == 404
    with app.state.database.connect() as db:
        assert db.execute('SELECT count(*) FROM playlist_items').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM videos').fetchone()[0] == 4


def test_playlist_scope_full_queue_filters_unavailable_and_revision(service):
    app, client, headers, ids = seed(service, 105)
    order = ids[::-1]
    playlist = client.post('/api/playlists',headers=headers,json={'name':'Long mix','ids':order}).json()
    identity = playlist['id']
    params = {'playlist':identity,'limit':48}
    page = client.get('/api/videos',params=params,headers=headers).json()
    assert page['total'] == 105 and [r['id'] for r in page['items']] == order[:48]
    queue = client.post('/api/queue',headers=headers,json={'playlist':identity}).json()['ids']
    assert queue == order
    shuffled = client.post('/api/queue',headers=headers,json={'playlist':identity,'shuffle':True,'start':order[5]}).json()['ids']
    assert shuffled[0] == order[5] and set(shuffled) == set(order) and len(shuffled) == 105
    filtered = client.get('/api/videos',params={'playlist':identity,'year':1991,'q':'Band'},headers=headers).json()
    assert all(r['year'] == 1991 for r in filtered['items']) and filtered['total'] > 0
    with app.state.database.connect() as db:
        db.execute('UPDATE videos SET available=0 WHERE id=?',(order[0],))
    detail = client.get('/api/playlists/'+identity,headers=headers).json()
    assert detail['count'] == 105 and detail['available_count'] == 104
    assert detail['items'][0]['available'] is False
    queue = client.post('/api/queue',headers=headers,json={'playlist':identity}).json()['ids']
    assert queue == order[1:]
    client.put('/api/playlists/'+identity,headers=headers,json={'name':'New order','ids':ids,'version':1})
    assert client.get('/api/videos',params={**params,'offset':48,'revision':page['revision']},headers=headers).status_code == 409
    assert client.get('/api/videos?playlist=missing',headers=headers).status_code == 404
    assert client.post('/api/queue',headers=headers,json={'playlist':'missing'}).status_code == 404
    assert client.post('/api/queue',headers=headers,json={'playlist':identity,'start':order[0]}).status_code == 409


@pytest.mark.parametrize('body',[{'name':'   '},{'name':'x'*121},{'name':'Mix','ids':['x','x']},{'name':'Mix','ids':['x']*5001}])
def test_playlist_validation(service,body):
    app, client, _ = service
    headers = login(app, client)
    assert client.post('/api/playlists',headers=headers,json=body).status_code == 422
    assert client.get('/api/playlists',headers=headers).json() == {'items':[]}


def test_empty_playlist_and_revocation(service):
    app, client, headers, ids = seed(service)
    playlist = client.post('/api/playlists',headers=headers,json={'name':'Empty'}).json()
    assert playlist['count'] == 0 and playlist['thumbnail'] is None
    assert client.post('/api/queue',headers=headers,json={'playlist':playlist['id']}).json()['ids'] == []
    client.delete('/api/session',headers=headers)
    assert client.get('/api/playlists',headers=headers).status_code == 401
    assert client.put('/api/playlists/'+playlist['id'],headers=headers,json={'name':'Hijacked','version':1}).status_code == 401


def test_studio_packaged_and_private_api(service):
    _, client, _ = service
    response = client.get('/studio/')
    assert response.status_code == 200 and 'Playlist studio' in response.text
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert client.get('/api/playlists').headers['cache-control'] == 'no-store'
    assert client.get('/studio/../../database.py').status_code == 404


def test_starter_seeding_is_selective_and_never_overwrites_edits(service):
    from mvideo.playlists import starter_playlists
    app, _, root = service
    for name in ['2 Unlimited - No Limit (1993).mp4','2 Unlimited - An Unselected Song (1993).mp4']:
        (root/name).write_bytes(b'x')
    app.state.library.scan()
    preview = starter_playlists(app.state.database)
    assert preview[0]['matched'] == 1 and Playlists(app.state.database).list() == []
    result = starter_playlists(app.state.database,apply=True)[0]
    store = Playlists(app.state.database)
    detail = store.get(result['id'])
    assert len(detail['items']) == 1 and detail['items'][0]['title'] == 'No Limit'
    store.save('My renamed mix','Edited',[],identity=result['id'],version=1)
    assert starter_playlists(app.state.database,apply=True)[0]['seed_skipped']
    assert len(store.list()) == 1 and store.get(result['id'])['name'] == 'My renamed mix'
    store.delete(result['id'],2)
    assert starter_playlists(app.state.database,apply=True)[0]['seed_skipped']
    assert store.list() == []
