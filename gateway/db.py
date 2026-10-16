"""Events, water points, villages and hazards; two backends. SQL_CONN set -> Azure SQL (pyodbc), else SQLite file.
ponytail: SQLite exists so `func start` works without Azure; set SQL_CONN at the hackathon."""
import os, sqlite3, csv, math

CONN = os.environ.get("SQL_CONN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _csv(name):
    with open(os.path.join(ROOT, "data", name)) as f:
        return list(csv.DictReader(f))


_ready = False


def _connect():
    global _ready
    if CONN:
        import pyodbc
        return pyodbc.connect(CONN)
    c = sqlite3.connect(os.path.join(ROOT, "db", "events.db"))
    if _ready:
        return c
    c.execute("""CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT CURRENT_TIMESTAMP, channel TEXT, sender TEXT, lang TEXT, body TEXT, reply TEXT, village TEXT, point TEXT)""")
    have = {r[1] for r in c.execute("PRAGMA table_info(events)")}
    for col in sorted({"village", "point"} - have):  # an events.db from before the map followed the caller
        c.execute(f"ALTER TABLE events ADD COLUMN {col} TEXT")
    c.execute("CREATE TABLE IF NOT EXISTS callers (sender TEXT PRIMARY KEY, lang TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS waterpoints (id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, village TEXT, lat REAL, lon REAL, status TEXT DEFAULT 'ok', updated TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("CREATE TABLE IF NOT EXISTS villages (name TEXT PRIMARY KEY, lat REAL, lon REAL)")
    c.execute("""CREATE TABLE IF NOT EXISTS hazards (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT DEFAULT CURRENT_TIMESTAMP,
        village TEXT, point TEXT, kind TEXT, body TEXT, reporter TEXT)""")
    # the seed files are the registry: when they name other places (the move from Kibaha to Muyinga), start over from them
    rows = _csv("waterpoints.csv")
    if {r[0] for r in c.execute("SELECT name FROM waterpoints")} != {r["name"] for r in rows}:
        c.execute("DELETE FROM waterpoints")
        c.executemany("INSERT INTO waterpoints(name,village,lat,lon,status) VALUES (?,?,?,?,?)",
                      [(r["name"], r["village"], float(r["lat"]), float(r["lon"]), r["status"]) for r in rows])
    c.execute("DELETE FROM villages")
    c.executemany("INSERT INTO villages(name,lat,lon) VALUES (?,?,?)",
                  [(r["name"], float(r["lat"]), float(r["lon"])) for r in _csv("villages.csv")])
    c.commit()
    _ready = True
    return c


def _top(n):  # SQL dialect difference in one place
    return (f"SELECT TOP ({n})", "") if CONN else ("SELECT", f" LIMIT {n}")


def log(channel, sender, lang, body, reply, village=None, point=None):
    """village/point: the place the turn was about; the map follows the newest one."""
    with _connect() as c:
        c.execute("INSERT INTO events(channel,sender,lang,body,reply,village,point) VALUES (?,?,?,?,?,?,?)",
                  (channel, sender, lang, body, reply, village, point))
        c.commit()


def events(n=100):
    sel, lim = _top(n)
    keys = ["id", "ts", "channel", "sender", "lang", "body", "reply", "village", "point"]
    with _connect() as c:
        rows = c.execute(f"{sel} {','.join(keys)} FROM events ORDER BY id DESC{lim}").fetchall()
    return [{k: None if v is None else str(v) for k, v in zip(keys, r)} for r in rows]


def villages():
    with _connect() as c:
        rows = c.execute("SELECT name,lat,lon FROM villages").fetchall()
    return [dict(zip(["name", "lat", "lon"], r)) for r in rows]


def add_hazard(village, point, kind, body, reporter):
    """A danger on the way from `village` to the water point `point`. reporter: a hash, never the number."""
    with _connect() as c:
        c.execute("INSERT INTO hazards(village,point,kind,body,reporter) VALUES (?,?,?,?,?)", (village, point, kind, body, reporter))
        c.commit()


def hazards(n=50):
    sel, lim = _top(n)
    keys = ["id", "ts", "village", "point", "kind", "body"]  # the reporter hash stays in the database
    with _connect() as c:
        rows = c.execute(f"{sel} {','.join(keys)} FROM hazards ORDER BY id DESC{lim}").fetchall()
    return [dict(zip(keys, map(str, r))) for r in rows]


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


def distance_km(a, b):
    """Great-circle distance. ponytail: straight line, roads are longer."""
    r = 6371
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def walk_minutes(a, b):
    """At 4 km/h, rounded to 5 minutes: a straight-line estimate, a round number says so. Never 0."""
    return max(5, 5 * round(distance_km(a, b) / 4 * 60 / 5))
