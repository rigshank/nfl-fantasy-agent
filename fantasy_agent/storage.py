"""Lightweight TTL cache and actual provider usage records; no token budgets."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time


class BudgetExceeded(RuntimeError):
    pass


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cache (
                  key TEXT PRIMARY KEY, value TEXT NOT NULL, created REAL NOT NULL,
                  expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS usage (
                  id INTEGER PRIMARY KEY, provider TEXT NOT NULL,
                  created REAL NOT NULL, tokens INTEGER NOT NULL DEFAULT 0,
                  input_tokens INTEGER NOT NULL DEFAULT 0,
                  output_tokens INTEGER NOT NULL DEFAULT 0,
                  thinking_tokens INTEGER NOT NULL DEFAULT 0);
            """)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=15)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get(self, key: str, stale=False):
        with self.db() as conn:
            row = conn.execute("SELECT value, created, expires FROM cache WHERE key=?", (key,)).fetchone()
        if row and (stale or row[2] > time.time()):
            return json.loads(row[0]), datetime.fromtimestamp(row[1], timezone.utc)
        return None

    def put(self, key: str, value, ttl: int):
        now = time.time()
        with self.db() as conn:
            conn.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?,?)",
                         (key, json.dumps(value), now, now + ttl))

    def record_request(self, provider: str) -> int:
        with self.db() as conn:
            return conn.execute("INSERT INTO usage(provider,created) VALUES(?,?)", (provider, time.time())).lastrowid

    def reserve(self, provider: str, windows: list[tuple[float, int]]) -> int:
        """Rolling rate guard for a documented upstream request limit only."""
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for since, limit in windows:
                count = conn.execute("SELECT count(*) FROM usage WHERE provider=? AND created>=?",
                                     (provider, since)).fetchone()[0]
                if count >= limit:
                    raise BudgetExceeded(f"{provider} request-rate guard reached; wait for the upstream rate window to reset and retry.")
            cur = conn.execute("INSERT INTO usage(provider,created) VALUES(?,?)", (provider, time.time()))
            return cur.lastrowid

    def record_tokens(self, event: int, total: int, prompt=0, output=0, thinking=0):
        with self.db() as conn:
            conn.execute("UPDATE usage SET tokens=?,input_tokens=?,output_tokens=?,thinking_tokens=? WHERE id=?",
                         (total, prompt, output, thinking, event))

    def usage(self):
        with self.db() as conn:
            return [dict(zip(("provider", "requests", "tokens", "input_tokens", "output_tokens", "thinking_tokens"), row))
                    for row in conn.execute("SELECT provider,count(*),sum(tokens),sum(input_tokens),sum(output_tokens),sum(thinking_tokens) FROM usage GROUP BY provider")]
