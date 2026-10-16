# Reach Gateway

Das Gerüst, das jede Hackathon-Idee braucht: SMS und Anruf rein, Datenbank, Antwort raus, Dashboard.
Was `handle()` in `function_app.py` antwortet, entscheidet ihr in Stunde 4.

```
Handy ──SMS/Anruf──▶ Twilio ──Webhook──▶ Azure Function ──▶ SQL (events)
                       ◀──TwiML────────┘                       │
                                             /api/dashboard ◀──┘
```

## Lokal starten (ohne Azure-Account)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
func start            # http://localhost:7071
./smoke.sh            # in zweitem Terminal: simuliert Twilio
open http://localhost:7071/api/dashboard
```

Ohne `SQL_CONN` landet alles in `events.db` (SQLite). Reicht für die ganze Entwicklung.

## Endpoints

| Route | Wer ruft | Was |
|---|---|---|
| `POST /api/sms` | Twilio | Speichert SMS, antwortet mit `handle(Body)` |
| `POST /api/voice` | Twilio | Tastenmenü; mit `Digits` speichert und antwortet per Sprache |
| `GET /api/events` | Dashboard | Letzte 100 Zeilen als JSON |
| `GET /api/dashboard` | Browser | Tabelle, aktualisiert alle 5 s |

## Vor dem Hackathon (spart die halbe erste Nacht)

1. **Twilio**: Account, eine Nummer mit SMS + Voice. Trial reicht. Alle Team-Handys unter
   *Verified Caller IDs* eintragen, sonst kommt nichts an.
2. **Azure**: Resource Group, Function App (Python 3.12, Consumption), Azure SQL (Basic reicht).
   `schema.sql` ausführen. Connection String als App Setting `SQL_CONN` eintragen.
3. **Deploy**: `func azure functionapp publish <name>`
4. **Twilio-Webhooks** auf die Nummer setzen:
   - Messaging → `https://<name>.azurewebsites.net/api/sms` (POST)
   - Voice → `https://<name>.azurewebsites.net/api/voice` (POST)
5. Einmal Round-Trip: SMS schicken, Echo zurück, Zeile im Dashboard. Bei jedem im Team.

Für lokales Testen mit echtem Handy ohne Deploy: `ngrok http 7071`, ngrok-URL als Webhook.

## Warum Twilio statt Azure Communication Services

ACS braucht Tage für eine SMS-fähige Nummer. Twilio geht sofort.
Für Uganda später: Africa's Talking (SMS, USSD, Voice, ugandische Shortcodes). Gehört auf die Betrieb-Folie.

## Stunde 4: Idee einbauen

- `handle(text)` in `function_app.py`: Parser und Antwort.
- `db.store(..., kind=, data=)`: strukturierte Daten mitschreiben.
- Dashboard: Spalten ergänzen, Karte erst, wenn die Idee eine braucht.

## Twilio-Credentials

`TWILIO_ACCOUNT_SID` und `TWILIO_AUTH_TOKEN` in `local.settings.json` (lokal) bzw. als App Settings (Azure).
`TWILIO_VALIDATE=1` in Azure setzen, dann werden nur signierte Twilio-Requests angenommen. Lokal `0`, sonst schlägt `smoke.sh` fehl.
