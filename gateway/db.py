"""Two tables, two backends. SQL_CONN set -> Azure SQL (pyodbc), else SQLite file.
ponytail: SQLite exists so `func start` works without Azure; set SQL_CONN at the hackathon."""
import os, sqlite3, csv, math

CONN = os.environ.get("SQL_CONN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _connect():
    if CONN:
        import pyodbc
        return pyodbc.connect(CONN)
    c = sqlite3.connect(os.path.join(ROOT, "db", "events.db"))
    c.execute("""CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT CURRENT_TIMESTAMP, channel TEXT, sender TEXT, lang TEXT, body TEXT, reply TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS callers (sender TEXT PRIMARY KEY, lang TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS waterpoints (id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, village TEXT, lat REAL, lon REAL, status TEXT DEFAULT 'ok', updated TEXT DEFAULT CURRENT_TIMESTAMP)""")
    if not c.execute("SELECT 1 FROM waterpoints LIMIT 1").fetchone():
        with open(os.path.join(ROOT, "data", "waterpoints.csv")) as f:
            c.executemany("INSERT INTO waterpoints(name,village,lat,lon,status) VALUES (?,?,?,?,?)",
                          [(r["name"], r["village"], float(r["lat"]), float(r["lon"]), r["status"]) for r in csv.DictReader(f)])
    return c


def _top(n):  # SQL dialect difference in one place
    return (f"SELECT TOP ({n})", "") if CONN else ("SELECT", f" LIMIT {n}")


def log(channel, sender, lang, body, reply):
    with _connect() as c:
        c.execute("INSERT INTO events(channel,sender,lang,body,reply) VALUES (?,?,?,?,?)", (channel, sender, lang, body, reply))
        c.commit()


def events(n=100):
    sel, lim = _top(n)
    with _connect() as c:
        rows = c.execute(f"{sel} id,ts,channel,sender,lang,body,reply FROM events ORDER BY id DESC{lim}").fetchall()
    return [dict(zip(["id", "ts", "channel", "sender", "lang", "body", "reply"], map(str, r))) for r in rows]


def waterpoints():
    with _connect() as c:
        rows = c.execute("SELECT id,name,village,lat,lon,status,updated FROM waterpoints").fetchall()
    return [dict(zip(["id", "name", "village", "lat", "lon", "status", "updated"], r)) for r in rows]


def set_status(wp_id, status):
    with _connect() as c:
        c.execute("UPDATE waterpoints SET status=?, updated=CURRENT_TIMESTAMP WHERE id=?", (status, wp_id))
        c.commit()


def get_lang(sender):
    with _connect() as c:
        r = c.execute("SELECT lang FROM callers WHERE sender=?", (sender,)).fetchone()
    return r[0] if r else None


def set_lang(sender, lang):
    with _connect() as c:
        c.execute("DELETE FROM callers WHERE sender=?", (sender,))
        c.execute("INSERT INTO callers(sender,lang) VALUES (?,?)", (sender, lang))
        c.commit()


def walk_minutes(a, b):
    """Great-circle distance at 4 km/h. ponytail: straight line, roads are longer."""
    r = 6371
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)) / 4 * 60)
