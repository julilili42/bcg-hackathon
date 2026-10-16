-- Azure SQL. Eine Tabelle, bewusst dumm. Spalten kind/data werden befüllt, sobald die Idee steht.
CREATE TABLE events (
  id      INT IDENTITY PRIMARY KEY,
  ts      DATETIME2 DEFAULT SYSUTCDATETIME(),
  channel VARCHAR(8),        -- 'sms' | 'voice'
  sender  VARCHAR(20),
  body    NVARCHAR(500),     -- Rohtext bzw. Tastendruck
  kind    VARCHAR(20) NULL,
  data    NVARCHAR(MAX) NULL -- JSON
);
