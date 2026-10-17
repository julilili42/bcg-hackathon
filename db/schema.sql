-- Azure SQL. Local dev uses SQLite with the same shape (see db.py).
CREATE TABLE events (
  id      INT IDENTITY PRIMARY KEY,
  ts      DATETIME2 DEFAULT SYSUTCDATETIME(),
  channel VARCHAR(8),        -- 'sms' | 'voice'
  sender  VARCHAR(20),
  lang    VARCHAR(2),        -- 'sw' | 'en' | 'de' | 'fr'
  body    NVARCHAR(500),     -- what the caller said / wrote
  reply   NVARCHAR(500),     -- what we answered
  village NVARCHAR(80),      -- the place the turn was about: the map follows the newest
  point   NVARCHAR(80),
  kind    VARCHAR(8),        -- 'status' | 'hazard' | 'query': one message in the feed per status or hazard
  detail  VARCHAR(12)        -- the status (ok/broken/empty) or the hazard kind
);
CREATE TABLE waterpoints (
  id      INT IDENTITY PRIMARY KEY,
  name    NVARCHAR(80),
  village NVARCHAR(80),
  lat     FLOAT, lon FLOAT,
  status  VARCHAR(8) DEFAULT 'ok',   -- 'ok' | 'broken' | 'empty'
  updated DATETIME2 DEFAULT SYSUTCDATETIME()
);
CREATE TABLE callers (          -- language a phone number chose, asked only on the first call
  sender  VARCHAR(40) PRIMARY KEY,
  lang    VARCHAR(2)
);
CREATE TABLE villages (        -- data/villages.csv, OpenStreetMap
  name    NVARCHAR(80) PRIMARY KEY,
  lat     FLOAT, lon FLOAT
);
CREATE TABLE hazards (         -- a danger on the way from a village to a water point
  id       INT IDENTITY PRIMARY KEY,
  ts       DATETIME2 DEFAULT SYSUTCDATETIME(),
  village  NVARCHAR(80),
  point    NVARCHAR(80),
  kind     VARCHAR(12),        -- 'harassment' | 'blocked' | 'animals' | 'other'
  body     NVARCHAR(500),      -- the caller's words
  reporter VARCHAR(40)         -- hash of the number, never the number
);
