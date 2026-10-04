from contextlib import contextmanager

from fastapi.testclient import TestClient

from mvideo.api import create_app
from mvideo.config import Settings
from mvideo.database import Database
from mvideo.library import Library


def test_existing_catalog_migrates_to_indexed_home_status_and_queue(tmp_path, monkeypatch):
    root = tmp_path/'media'; root.mkdir()
    settings = Settings(root, tmp_path/'state'); settings.prepare()
    database = Database(settings.state/'library.sqlite3')
    library = Library(settings, database)
    library.probe = lambda path: {'format': {'duration': '10'}, 'streams': []}
    for name in ('Band - Zulu (2000)', 'band - Alpha (2001)', 'Other - Known (1985)', 'Other - Unknown'):
        (root/(name+'.mp4')).write_bytes(b'x')
    library.scan()
    # Simulate an existing installation before the new indexes are introduced.
    with database.connect() as db:
        db.execute('DROP INDEX IF EXISTS videos_browse')
        db.execute('DROP INDEX IF EXISTS videos_available_year')
    expected = library.videos(limit=100)
    expected_ids = [item['id'] for item in expected['items']]

    app = create_app(settings)
    queries = []
    connect = app.state.database.connect

    @contextmanager
    def traced_connect():
        with connect() as db:
            db.set_trace_callback(queries.append)
            yield db

    monkeypatch.setattr(app.state.database, 'connect', traced_connect)
    token = app.state.auth.pair(app.state.auth.pair_code())
    headers = {'Authorization': 'Bearer '+token}
    with TestClient(app) as client:
        page = client.get('/api/videos?limit=2&offset=1', headers=headers).json()
        queue = client.post('/api/queue', headers=headers, json={'shuffle': False}).json()
        status = client.get('/api/status', headers=headers).json()
        assert [item['id'] for item in page['items']] == expected_ids[1:3]
        assert page['total'] == 4 and page['next_offset'] == 3
        assert page['revision'] == queue['revision'] == status['revision'] == expected['revision']
        assert queue['ids'] == expected_ids
        assert status['total'] == 4 and status['unknown_years'] == 1

    # Inspect the SQL actually used by the endpoints. Counts and full queues
    # should stay in compact indexes; Home should avoid sorting the whole table.
    catalog_queries = {sql for sql in queries if sql.startswith((
        'SELECT count(*) FROM videos WHERE available=1',
        'SELECT * FROM videos WHERE available=1 ORDER BY',
        'SELECT id FROM videos WHERE available=1 ORDER BY',
    ))}
    assert len(catalog_queries) == 4
    with connect() as db:
        for sql in catalog_queries:
            plan = ' '.join(row['detail'] for row in db.execute('EXPLAIN QUERY PLAN '+sql))
            assert 'SEARCH videos USING' in plan, (sql, plan)
            assert 'TEMP B-TREE' not in plan, (sql, plan)
            if not sql.startswith('SELECT *'):
                assert 'COVERING INDEX' in plan, (sql, plan)
