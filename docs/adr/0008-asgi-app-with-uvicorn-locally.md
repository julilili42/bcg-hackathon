# ADR 0008 — One FastAPI (ASGI) app, wrapped by Azure Functions, served by uvicorn locally

**Status:** accepted, 2026-10-16

## Context
Azure Functions Core Tools and cloudflared were not installed on the first development machine, and
tests should not depend on the Functions host. ADR 0001 keeps Azure Functions as the deployment target.

## Decision
The application is a FastAPI app (`reach.app.create_app`). `api/function_app.py` wraps it with
`azure.functions.AsgiFunctionApp`; `host.json` sets an empty route prefix so `/api/...` paths are the
same locally and in Azure. Locally and in CI the app runs under uvicorn (`make dev`), tests use
FastAPI's `TestClient`, and `scripts/with_server.py` starts and stops a real server for smoke runs.

## Consequences
- No Functions runtime needed for development, CI, or the demo machine.
- Azure deployment is unchanged in shape; `func start` still works when Core Tools are present.
- FastAPI also gives `/api/docs` for free; the hand-written `docs/api/openapi.yaml` stays the contract
  and `test_contract.py` keeps the two in step.
