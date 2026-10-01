"""Shared, ordered playlists. Every write is atomic and checks the editor version."""
import time
import uuid


class PlaylistConflict(ValueError):
    pass


class Playlists:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def require(db, identity, version=None):
        row = db.execute('SELECT * FROM playlists WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise FileNotFoundError('Playlist no longer exists')
        if version is not None and row['version'] != version:
            raise PlaylistConflict('This playlist changed in another editor. Reload it before saving.')
        return dict(row)

    @staticmethod
    def summary(db, row):
        result = dict(row)
        stats = db.execute('''SELECT count(*) AS count, coalesce(sum(v.available),0) AS available_count
            FROM playlist_items i JOIN videos v ON v.id=i.video_id WHERE i.playlist_id=?''', (row['id'],)).fetchone()
        result.update(dict(stats))
        cover = db.execute('''SELECT v.id FROM playlist_items i JOIN videos v ON v.id=i.video_id
            WHERE i.playlist_id=? AND v.available=1 ORDER BY i.position LIMIT 1''', (row['id'],)).fetchone()
        result['cover_id'] = cover['id'] if cover else None
        return result

    def list(self):
        with self.database.connect() as db:
            db.execute('BEGIN')
            return [self.summary(db, r) for r in db.execute('SELECT * FROM playlists ORDER BY created_at,id').fetchall()]

    def get(self, identity):
        with self.database.connect() as db:
            db.execute('BEGIN')
            result = self.summary(db, self.require(db, identity))
            result['items'] = [dict(r) for r in db.execute('''SELECT v.* FROM playlist_items i
                JOIN videos v ON v.id=i.video_id WHERE i.playlist_id=? ORDER BY i.position''', (identity,))]
            return result

    def save(self, name, description, ids, identity=None, version=None, seed_key=None):
        name, description = name.strip(), description.strip()
        if not name or len(name) > 120 or len(description) > 2000:
            raise ValueError('Use a name of 1–120 characters and a description of at most 2000 characters')
        if len(ids) > 5000 or len(ids) != len(set(ids)):
            raise ValueError('A playlist supports up to 5,000 distinct videos')
        now = int(time.time())
        with self.database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if seed_key is not None:
                seeded = db.execute('SELECT playlist_id FROM playlist_seeds WHERE key=?', (seed_key,)).fetchone()
                if seeded is not None:
                    return {'id':seeded['playlist_id'], 'name':name, 'seed_skipped':True}
            if identity is not None:
                if version is None:
                    raise PlaylistConflict('A playlist version is required')
                self.require(db, identity, version)
            # Keep unavailable existing entries, but do not silently accept unknown IDs.
            known = {r['id'] for r in db.execute('SELECT id FROM videos')}
            if any(i not in known for i in ids):
                raise ValueError('One or more videos are not in this library')
            if identity is None:
                identity = uuid.uuid4().hex
                db.execute('INSERT INTO playlists VALUES(?,?,?,1,?,?)', (identity, name, description, now, now))
            else:
                db.execute('UPDATE playlists SET name=?,description=?,version=version+1,updated_at=? WHERE id=?',
                           (name, description, now, identity))
                db.execute('DELETE FROM playlist_items WHERE playlist_id=?', (identity,))
            db.executemany('INSERT INTO playlist_items VALUES(?,?,?)', [(identity, video_id, n) for n, video_id in enumerate(ids)])
            if seed_key is not None:
                db.execute('INSERT INTO playlist_seeds VALUES(?,?)', (seed_key, identity))
            db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")

            # Return the version written by this transaction, never a later editor's version.
            return self.summary(db, self.require(db, identity))

    def delete(self, identity, version):
        with self.database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require(db, identity, version)
            db.execute('DELETE FROM playlists WHERE id=?', (identity,))
            db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")


def starter_playlists(database, apply=False):
    """Resolve explicit artist/song recipes against this catalog, never whole artists."""
    import json
    import unicodedata
    from pathlib import Path

    def normalize(value):
        return ''.join(c for c in unicodedata.normalize('NFKC', value or '').casefold() if c.isalnum())

    with database.connect() as db:
        rows = db.execute('SELECT * FROM videos WHERE available=1 ORDER BY (probe_error IS NOT NULL), id').fetchall()
    index = {}
    for row in rows:
        index.setdefault((normalize(row['artist']),normalize(row['title'])),[]).append(row['id'])
    recipes = json.loads((Path(__file__).parent/'data'/'starter-playlists.json').read_text(encoding='utf-8'))
    results = []
    for recipe in recipes:
        ids, missing, duplicates = [], [], []
        for track in recipe['tracks']:
            matches = index.get((normalize(track['artist']),normalize(track['title'])),[])
            if not matches:
                missing.append(track['artist']+' — '+track['title'])
            elif matches[0] not in ids:
                ids.append(matches[0])
                if len(matches)>1: duplicates.append(track['artist']+' — '+track['title'])
        result = {'name':recipe['name'],'matched':len(ids),'missing':missing,'alternate_versions':duplicates}
        if apply and ids:
            result.update(Playlists(database).save(recipe['name'],recipe['description'],ids,seed_key=recipe['key']))
        results.append(result)
    return results
