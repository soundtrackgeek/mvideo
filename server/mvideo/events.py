"""Small replay window for artwork completions; catalog state stays in SQLite."""
from collections import deque
import asyncio
import threading
from fastapi.sse import ServerSentEvent


class LibraryEvents:
    def __init__(self, database, auth):
        self.database, self.auth = database, auth
        self.lock = threading.Lock()
        self.sequence = 0
        self.artwork = deque(maxlen=128)

    def artwork_ready(self, artist):
        with self.lock:
            self.sequence += 1
            self.artwork.append((self.sequence, artist))

    def snapshot(self):
        with self.database.connect() as db:
            db.execute('BEGIN')
            revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
            total = db.execute('SELECT count(*) FROM videos WHERE available=1').fetchone()[0]
        return {'revision': revision, 'total': total}

    def artwork_since(self, cursor):
        with self.lock:
            missed = bool(self.artwork and cursor < self.artwork[0][0] - 1)
            return self.sequence, missed, [(seq, artist) for seq, artist in self.artwork if seq > cursor]

    async def stream(self, sid, *, interval=2):
        # Read the cursor before the snapshot: completions during connection setup
        # must still be delivered. A new snapshot tells clients to recheck artwork.
        cursor, _, _ = self.artwork_since(0)
        previous = await asyncio.to_thread(self.snapshot)
        yield ServerSentEvent(event='snapshot', data=previous)
        while True:
            await asyncio.sleep(interval)
            if not await asyncio.to_thread(self.auth.valid_hash, sid):
                return
            current = await asyncio.to_thread(self.snapshot)
            cursor, missed, artwork = self.artwork_since(cursor)
            if missed:
                yield ServerSentEvent(event='snapshot', data=current)
            elif current != previous:
                yield ServerSentEvent(event='library-changed', data=current)
            previous = current
            if not missed:
                for sequence, artist in artwork:
                    yield ServerSentEvent(event='artwork-ready', data={'artist': artist, 'sequence': sequence})
