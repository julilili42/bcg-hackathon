# API contract

`openapi.yaml` is written in M0 by the Tech Lead with WS-C and is the contract between the Functions
app and the web map. Endpoints planned (see `docs/02-architecture.md` → Channel flows → Web):

- `GET /api/health`
- `GET /api/domains`
- `GET /api/entities?domain=&bbox=` → GeoJSON FeatureCollection
- `GET /api/entities/{id}`
- `GET /api/reports?domain=&since=&limit=`
- `POST /api/reports` (web report form)
- `GET /api/stats?domain=`

Twilio webhooks (`/api/voice`, `/api/voice/handle`, `/api/sms`) are not part of the OpenAPI contract;
they are covered by recorded-payload smoke tests.
