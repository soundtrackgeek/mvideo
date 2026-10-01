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
CREATE TABLE IF NOT EXISTS playlists(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 version INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS playlist_items(
 playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
 video_id TEXT NOT NULL REFERENCES videos(id), position INTEGER NOT NULL,
 PRIMARY KEY(playlist_id, video_id), UNIQUE(playlist_id, position)
);
CREATE TABLE IF NOT EXISTS playlist_seeds(
 key TEXT PRIMARY KEY, playlist_id TEXT REFERENCES playlists(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS audio_loudness(
 video_id TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
 source_size INTEGER NOT NULL, source_mtime INTEGER NOT NULL, analysis_version TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('measured','below_gate','no_audio','error')),
 integrated_lufs REAL, true_peak_dbtp REAL, loudness_range_lu REAL, threshold_lufs REAL,
 audio_stream_index INTEGER, ffmpeg_version TEXT NOT NULL, measured_at INTEGER NOT NULL, error TEXT
);
CREATE TABLE IF NOT EXISTS filename_renames(
 id INTEGER PRIMARY KEY, old_id TEXT NOT NULL, new_id TEXT NOT NULL,
 old_path TEXT NOT NULL, new_path TEXT NOT NULL,
 source_size INTEGER NOT NULL, source_mtime INTEGER NOT NULL,
 original_row TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','complete')),
 action TEXT NOT NULL CHECK(action IN ('rename','hold')),
 created_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS filename_renames_pending ON filename_renames(old_id) WHERE state='pending';
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
        db.execute("PRAGMA foreign_keys=ON")
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
