"""Saved analyst chats, isolated by browser identity, league and selected team."""
import hashlib
import json
import time
from uuid import uuid4


class Conversations:
    def __init__(self,store,browser_id,league_id,roster_id):
        self.store=store
        self.scope=hashlib.sha256(json.dumps([browser_id,league_id,roster_id]).encode()).hexdigest()
        with store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS analyst_conversations (
                id TEXT PRIMARY KEY, scope TEXT NOT NULL, title TEXT NOT NULL,
                updated REAL NOT NULL, messages TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS analyst_conversations_scope ON analyst_conversations(scope,updated DESC)")

    def list(self):
        with self.store.db() as db:
            rows=db.execute("SELECT id,title,updated FROM analyst_conversations WHERE scope=? AND messages != '[]' ORDER BY updated DESC,id DESC",(self.scope,)).fetchall()
        return [dict(zip(("id","title","updated"),row)) for row in rows]

    def messages(self,conversation_id):
        with self.store.db() as db:
            row=db.execute("SELECT messages FROM analyst_conversations WHERE scope=? AND id=?",(self.scope,conversation_id)).fetchone()
        return json.loads(row[0]) if row else None

    def create(self,messages=None):
        cid=uuid4().hex
        messages=messages or []
        with self.store.db() as db:
            db.execute("INSERT INTO analyst_conversations VALUES(?,?,?,?,?)",(cid,self.scope,self.title(messages),time.time(),json.dumps(messages)))
        return cid

    def save(self,conversation_id,messages):
        with self.store.db() as db:
            changed=db.execute("UPDATE analyst_conversations SET title=?,updated=?,messages=? WHERE id=? AND scope=?",
                (self.title(messages),time.time(),json.dumps(messages),conversation_id,self.scope)).rowcount
        if not changed:raise ValueError("Conversation is no longer available for this team.")

    @staticmethod
    def title(messages):
        text=next((m["content"] for m in messages if m.get("role")=="user"),"")
        text=" ".join(text.split())
        return text[:57]+"…" if len(text)>58 else text or "New conversation"
