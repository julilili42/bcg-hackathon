-- Azure SQL. Local dev uses SQLite with the same shape (see db.py).
CREATE TABLE events (
  id      INT IDENTITY PRIMARY KEY,
  ts      DATETIME2 DEFAULT SYSUTCDATETIME(),
  channel VARCHAR(8),        -- 'sms' | 'voice'
  sender  VARCHAR(20),
  lang    VARCHAR(2),        -- 'sw' | 'en'
  body    NVARCHAR(500),     -- what the caller said / wrote
  reply   NVARCHAR(500)      -- what we answered
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
