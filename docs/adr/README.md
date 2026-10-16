# Architecture decision records

One file per decision, numbered, never edited after acceptance; supersede with a new ADR.
Format: Context → Decision → Consequences. Keep each under a page.

| # | Decision | Status |
|---|---|---|
| 0001 | Azure Functions + Azure SQL, local-first with SQLite | accepted |
| 0002 | Generic domain model configured per use case | accepted |
| 0003 | Seed from WPDx and Tanzania HFR open data | accepted |
| 0004 | Reporter identity stored as salted hash only | accepted |
| 0005 | Understanding via Claude Opus 5.5 with keyword fallback; Twilio STT; local TTS with Azure Speech option | accepted |
| 0006 | Status derived from weighted reports with decay, not last-write-wins | accepted |
| 0007 | Parallel Claude Code sessions per workstream, contracts first | accepted |
| 0008 | One FastAPI (ASGI) app, wrapped by Azure Functions, served by uvicorn locally | accepted |
| 0009 | Imported and demo baselines are weak priors that one live report overrides | accepted |
| 0010 | Follow-up questions only when a slot is missing | accepted |
