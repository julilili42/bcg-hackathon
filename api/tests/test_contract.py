"""The hand-written OpenAPI file is the contract. Routes and response shapes must match it."""

from pathlib import Path
from typing import Any

import jsonschema
import yaml
from fastapi.testclient import TestClient

from reach.settings import REPO_ROOT

SPEC_PATH = REPO_ROOT / "docs" / "api" / "openapi.yaml"


def load_spec() -> dict[str, Any]:
    data = yaml.safe_load(Path(SPEC_PATH).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def resolver(spec: dict[str, Any]) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator({"$ref": "#/components/schemas/Health", **spec})


def validate(spec: dict[str, Any], schema_ref: dict[str, Any], payload: Any) -> None:
    schema = {**schema_ref, "components": spec["components"]}
    jsonschema.Draft202012Validator(schema).validate(payload)


def test_every_spec_path_exists_in_the_app_and_vice_versa(client: TestClient) -> None:
    spec = load_spec()
    spec_ops = {
        (path, method.upper())
        for path, ops in spec["paths"].items()
        for method in ops
        if method.lower() in {"get", "post", "put", "delete", "patch"}
    }
    generated = client.app.openapi()  # type: ignore[attr-defined]
    app_ops = {
        (path, method.upper())
        for path, ops in generated["paths"].items()
        for method, op in ops.items()
        if "web" in (op.get("tags") or [])
    }
    assert spec_ops == app_ops, f"spec-only: {spec_ops - app_ops}; app-only: {app_ops - spec_ops}"


def test_get_responses_match_schemas(client: TestClient) -> None:
    spec = load_spec()
    client.post("/api/sms", data={"From": "+15005550006", "Body": "Shule imeharibika"})
    cases = [
        ("/api/health", "/api/health"),
        ("/api/domains", "/api/domains"),
        ("/api/entities?domain=water", "/api/entities"),
        ("/api/entities/t:shule", "/api/entities/{entity_id}"),
        ("/api/reports?domain=water", "/api/reports"),
        ("/api/stats?domain=water", "/api/stats"),
        ("/api/interactions", "/api/interactions"),
    ]
    for url, path in cases:
        schema = spec["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        response = client.get(url)
        assert response.status_code == 200, url
        validate(spec, schema, response.json())


def test_post_report_matches_schema(client: TestClient) -> None:
    spec = load_spec()
    schema = spec["paths"]["/api/reports"]["post"]["responses"]["201"]["content"]["application/json"][
        "schema"
    ]
    response = client.post("/api/reports", json={"entity_id": "t:soko", "status": "ok"})
    assert response.status_code == 201
    validate(spec, schema, response.json())
    reset_schema = spec["paths"]["/api/admin/reset"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    validate(spec, reset_schema, client.post("/api/admin/reset", headers={"X-Admin-Token": "secret"}).json())
