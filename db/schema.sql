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
CREATE TABLE incidents (        -- a caller who said where they stand and which water point they cannot get water from
  id      INT IDENTITY PRIMARY KEY,
  ts      DATETIME2 DEFAULT SYSUTCDATETIME(),
  place   NVARCHAR(80),         -- the registry name they gave: a village or a water point
  lat     FLOAT, lon FLOAT,
  wp_id   INT,                  -- the water point they cannot use
  alt_id  INT,                  -- the nearest working one from where they stand, NULL when none works
  blocked BIT DEFAULT 0         -- 1: the way there is blocked (the pump itself may work), 0: the pump is down
);
