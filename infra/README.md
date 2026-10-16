# Deploying Reach to Azure (documented, not executed in the hackathon)

Decision D5: daily work is local. This is the path when a subscription is available.

## Shape

| Piece | Azure service | Notes |
|---|---|---|
| API + Twilio webhooks | Function App, Linux, Python 3.12, Premium EP1 | `api/function_app.py` wraps the FastAPI app (ASGI). `host.json` has an empty route prefix. |
| Database | Azure SQL serverless (General Purpose) | `DATABASE_URL=mssql+pyodbc:///?odbc_connect=<url-encoded conn string>`; `uv sync --extra azure` adds `pyodbc`. Schema is created by SQLAlchemy on first start (`init_db`). |
| Web map | Served from the Function App at `/` from `web/dist`, or Azure Static Web Apps | Build with `make build-web` before publishing. |
| Swahili voice | Azure AI Speech (`sw-TZ-RehemaNeural`) | Set `TTS_PROVIDER=azure`, `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`. Replaces the 300 MB local MMS models. |
| Secrets | App Settings or Key Vault references | `TWILIO_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `REPORTER_SALT`, `ADMIN_TOKEN`. Never in the repo. |

## Steps

```bash
# 1. resources (names are examples)
az group create -n rg-reach -l northeurope
az deployment group create -g rg-reach -f infra/main.bicep -p namePrefix=reach sqlAdminPassword='<strong>'

# 2. app settings (see api/local.settings.json.example for the full list)
az functionapp config appsettings set -g rg-reach -n reach-api --settings \
  TWILIO_VALIDATE=1 PUBLIC_BASE_URL=https://reach-api.azurewebsites.net \
  DATABASE_URL='mssql+pyodbc:///?odbc_connect=...' TTS_PROVIDER=azure AZURE_SPEECH_REGION=northeurope

# 3. build + publish
make build-web
cd api && uv export --no-dev --extra azure > requirements.txt && func azure functionapp publish reach-api

# 4. seed and point Twilio at it
DATABASE_URL='mssql+pyodbc:///?odbc_connect=...' PYTHONPATH=api uv run python -m reach.ingest.seed --reset
scripts/set_webhooks.sh https://reach-api.azurewebsites.net
```

## Known gaps before production

- `RateLimiter` is in memory: fine on one instance, needs a shared store when scaled out.
- Raw message text is kept; add the 30-day purge timer function described in ADR 0004.
- The web map is anonymous; add Entra ID or Static Web Apps auth for coordinators.
- SQLAlchemy `DateTime` columns are naive UTC; Azure SQL stores `datetime` with the same semantics.
