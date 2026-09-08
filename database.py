"""SilentRuins v5 SQLite store."""
from __future__ import annotations
import sqlite3, threading, time
from pathlib import Path

class Database:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init()

    def _init(self):
        with self.lock, self.conn:
            self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at INTEGER NOT NULL,
              mood TEXT, caption TEXT, music_file_id TEXT, image_url TEXT,
              quality INTEGER, status TEXT NOT NULL, error TEXT
            );
            CREATE TABLE IF NOT EXISTS tracks(
              file_id TEXT PRIMARY KEY, title TEXT, performer TEXT, mood TEXT,
              added_at INTEGER NOT NULL, play_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL,
              event_type TEXT NOT NULL, detail TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at);
            CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
            """)
            # Migrate databases created by older versions.
            for col, typ in (("image_url","TEXT"),("quality","INTEGER"),("error","TEXT")):
                try: self.conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {typ}")
                except sqlite3.OperationalError: pass

    def event(self, kind: str, detail: str = ""):
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO events(created_at,event_type,detail) VALUES(?,?,?)",(int(time.time()),kind,str(detail)[:2000]))

    def post_success(self, mood, caption, track_id=None, image_url=None, quality=None):
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO posts(created_at,mood,caption,music_file_id,image_url,quality,status) VALUES(?,?,?,?,?,?,?)",(int(time.time()),mood,caption,track_id,image_url,quality,"success"))

    def post_failed(self, mood, caption, error):
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO posts(created_at,mood,caption,status,error) VALUES(?,?,?,?,?)",(int(time.time()),mood,caption,"failed",str(error)[:2000]))

    def track_upsert(self, t):
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO tracks(file_id,title,performer,mood,added_at) VALUES(?,?,?,?,?) ON CONFLICT(file_id) DO UPDATE SET title=excluded.title,performer=excluded.performer,mood=excluded.mood",(t.get("file_id"),t.get("title"),t.get("performer"),t.get("mood"),int(t.get("added_at",time.time()))))

    def track_delete(self, file_id):
        with self.lock, self.conn: self.conn.execute("DELETE FROM tracks WHERE file_id=?",(file_id,))

    def track_played(self, file_id):
        with self.lock, self.conn: self.conn.execute("UPDATE tracks SET play_count=play_count+1 WHERE file_id=?",(file_id,))

    def summary(self):
        with self.lock:
            total=self.conn.execute("SELECT COUNT(*) FROM posts WHERE status='success'").fetchone()[0]
            failed=self.conn.execute("SELECT COUNT(*) FROM posts WHERE status='failed'").fetchone()[0]
            today=self.conn.execute("SELECT COUNT(*) FROM posts WHERE status='success' AND created_at>=?",(int(time.time())-86400,)).fetchone()[0]
            avg=self.conn.execute("SELECT AVG(quality) FROM posts WHERE status='success' AND quality IS NOT NULL").fetchone()[0]
            moods=self.conn.execute("SELECT mood,COUNT(*) c FROM posts WHERE status='success' GROUP BY mood ORDER BY c DESC").fetchall()
            top=self.conn.execute("SELECT title,performer,play_count FROM tracks ORDER BY play_count DESC,added_at DESC LIMIT 8").fetchall()
            tracks=self.conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
            return {"posts":total,"failed":failed,"today":today,"avg_quality":round(avg or 0),"tracks":tracks,"moods":[dict(x) for x in moods],"top_tracks":[dict(x) for x in top]}

    def close(self): self.conn.close()
