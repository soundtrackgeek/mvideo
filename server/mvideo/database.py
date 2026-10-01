from contextlib import contextmanager
from pathlib import Path
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES('revision',0);
CREATE TABLE IF NOT EXISTS videos(
 id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, size INTEGER NOT NULL, mtime INTEGER NOT NULL,
 artist TEXT, title TEXT NOT NULL, year INTEGER, raw_name TEXT NOT NULL, warnings TEXT NOT NULL,
 probe TEXT, probe_error TEXT, available INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS videos_artist ON videos(artist COLLATE NOCASE, id);
CREATE INDEX IF NOT EXISTS videos_year ON videos(year, id);
CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, artist, title, year,
 tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pairing(id INTEGER PRIMARY KEY CHECK(id=1), hash TEXT, expires INTEGER, attempts INTEGER);
CREATE TABLE IF NOT EXISTS metadata(artist TEXT PRIMARY KEY, data TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS identities(artist TEXT PRIMARY KEY, mbid TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS overrides(id TEXT PRIMARY KEY, artist TEXT, title TEXT NOT NULL, year INTEGER);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def revision(self):
        with self.connect() as db:
            return db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
