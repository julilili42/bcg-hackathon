# ADR 0001 — Azure Functions + Azure SQL, local-first with SQLite

**Status:** accepted, 2026-10-16

## Context
The prototype ran as an Azure Functions app (Python) with Azure SQL or SQLite. The team chose to keep
this shape (D4) but has no Azure subscription for daily work (D5). Twilio webhooks need a public URL.

## Decision
Keep the Azure Functions v2 Python programming model as the single backend. Run it locally with Azure
Functions Core Tools and SQLite via SQLAlchemy Core; the same schema runs on Azure SQL. Public URL for
the demo through a cloudflared tunnel owned by the demo owner. Deployment to Azure is documented in
`infra/` with a Bicep skeleton and not executed during the hackathon.

## Consequences
- One codebase, no rewrite if deployment happens later.
- SQLAlchemy Core abstracts SQLite/Azure SQL differences; avoid vendor-specific SQL (no `IDENTITY`,
  no `SYSUTCDATETIME()` in shared code).
- Cold starts and torch size matter only on Azure; locally irrelevant. Documented alternative:
  Azure AI Speech for TTS.
- Only one machine can receive real Twilio traffic at a time; everyone else uses recorded fixtures.
