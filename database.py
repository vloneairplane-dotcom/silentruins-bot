"""SQLite persistence layer for SilentRuins Bot v2."""
import sqlite3
import threading
import time
from pathlib import Path


class Database:
    def __init__(self, path: str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        with self.lock, self.conn:
            self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                mood TEXT,
                caption TEXT,
                music_file_id TEXT,
                status TEXT NOT NULL,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS tracks (
                file_id TEXT PRIMARY KEY,
                title TEXT,
                performer TEXT,
                mood TEXT,
                added_at INTEGER NOT NULL,
                play_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                detail TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at);
            CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
            CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
            """)

    def event(self, event_type, detail=""):
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO events(created_at,event_type,detail) VALUES(?,?,?)", (int(time.time()), event_type, str(detail)[:1000]))

    def post_start(self, mood, caption, music_file_id=None):
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO posts(created_at,mood,caption,music_file_id,status) VALUES(?,?,?,?,?)",
                (int(time.time()), mood, caption, music_file_id, "success")
            )
            return cur.lastrowid

    def post_failed(self, mood, caption, error):
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO posts(created_at,mood,caption,status,error) VALUES(?,?,?,?,?)",
                (int(time.time()), mood, caption, "failed", str(error)[:1000])
            )
            return cur.lastrowid

    def track_upsert(self, track):
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO tracks(file_id,title,performer,mood,added_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(file_id) DO UPDATE SET title=excluded.title,performer=excluded.performer,mood=excluded.mood",
                (track.get("file_id"), track.get("title"), track.get("performer"), track.get("mood"), int(track.get("added_at", time.time())))
            )

    def track_deleted(self, file_id):
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM tracks WHERE file_id=?", (file_id,))

    def track_played(self, file_id):
        with self.lock, self.conn:
            self.conn.execute("UPDATE tracks SET play_count=play_count+1 WHERE file_id=?", (file_id,))

    def summary(self):
        with self.lock:
            posts = self.conn.execute("SELECT COUNT(*) FROM posts WHERE status='success'").fetchone()[0]
            failed = self.conn.execute("SELECT COUNT(*) FROM posts WHERE status='failed'").fetchone()[0]
            today = int(time.time()) - 86400
            recent = self.conn.execute("SELECT COUNT(*) FROM posts WHERE status='success' AND created_at>=?", (today,)).fetchone()[0]
            tracks = self.conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
            top = self.conn.execute("SELECT title, performer, play_count FROM tracks ORDER BY play_count DESC, added_at DESC LIMIT 5").fetchall()
            moods = self.conn.execute("SELECT mood, COUNT(*) c FROM posts WHERE status='success' AND mood IS NOT NULL GROUP BY mood ORDER BY c DESC").fetchall()
            return {"posts": posts, "failed": failed, "today": recent, "tracks": tracks, "top_tracks": [dict(x) for x in top], "moods": [dict(x) for x in moods]}

    def close(self):
        with self.lock:
            self.conn.close()
