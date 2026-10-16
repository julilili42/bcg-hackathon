"""Eine Tabelle, zwei Backends. SQL_CONN gesetzt -> Azure SQL, sonst SQLite-Datei.
ponytail: SQLite nur damit `func start` ohne Azure läuft; am Hackathon SQL_CONN setzen."""
import os, sqlite3, json

CONN = os.environ.get("SQL_CONN", "")
SQLITE = os.path.join(os.path.dirname(__file__), "events.db")


def _connect():
    if CONN:
        import pyodbc
        return pyodbc.connect(CONN)
    c = sqlite3.connect(SQLITE)
    c.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT CURRENT_TIMESTAMP,
        channel TEXT, sender TEXT, body TEXT, kind TEXT, data TEXT)""")
    return c


def store(channel, sender, body, kind=None, data=None):
    with _connect() as c:
        c.execute("INSERT INTO events(channel,sender,body,kind,data) VALUES (?,?,?,?,?)",
                  (channel, sender, body, kind, json.dumps(data) if data else None))
        c.commit()


def recent(limit=100):
    with _connect() as c:
        rows = c.execute("SELECT id,ts,channel,sender,body,kind,data FROM events ORDER BY id DESC LIMIT ?"
                         if not CONN else
                         "SELECT TOP (?) id,ts,channel,sender,body,kind,data FROM events ORDER BY id DESC",
                         (limit,)).fetchall()
    return [dict(zip(["id", "ts", "channel", "sender", "body", "kind", "data"], map(str, r))) for r in rows]
