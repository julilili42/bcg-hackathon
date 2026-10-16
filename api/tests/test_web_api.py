from fastapi.testclient import TestClient

from reach.storage.repository import Repository


def test_health_and_domains(client: TestClient) -> None:
    h = client.get("/api/health").json()
    assert (
        h["status"] == "ok" and h["entities"] == 7 and h["understanding"] == "keywords" and h["tts"] == "none"
    )
    d = client.get("/api/domains").json()
    assert {x["id"] for x in d} == {"water", "health"}


def test_entities_geojson_and_bbox(client: TestClient) -> None:
    fc = client.get("/api/entities?domain=water").json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 5
    f = next(x for x in fc["features"] if x["id"] == "t:soko")
    assert f["geometry"]["coordinates"] == [39.07, -6.91]
    assert f["properties"]["current_status"] == "broken" and f["properties"]["verified"] is False
    assert (
        f["properties"]["status_label"] == {"en": "broken", "sw": "imeharibika"}
        and f["properties"]["is_good"] is False
    )
    small = client.get("/api/entities?domain=water&bbox=39.055,-6.905,39.065,-6.895").json()
    assert len(small["features"]) == 3
    assert client.get("/api/entities?domain=nope").status_code == 404
    assert client.get("/api/entities?domain=water&bbox=1,2").status_code == 422


def test_entity_detail_reports_and_alternatives(client: TestClient) -> None:
    r = client.get("/api/entities/t:soko").json()
    assert r["entity"]["properties"]["name"] == "Soko" and len(r["reports"]) == 1
    assert r["reports"][0]["reporter_hash"] == "seed"[:8] and r["alternatives"][0]["verified"] is False
    assert r["alternatives"][0]["name"] in {"Shule", "Kanisa", "Kisarawe Market Tap"}
    assert client.get("/api/entities/missing").status_code == 404


def test_post_report_changes_status_and_feeds(client: TestClient, seeded: Repository) -> None:
    created = client.post(
        "/api/reports",
        json={"entity_id": "t:shule", "status": "broken", "note": "handle snapped", "lang": "en"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["derived"]["status"] == "broken" and body["entity"]["properties"]["verified"] is True
    again = client.post("/api/reports", json={"entity_id": "t:shule", "status": "broken"}).json()
    assert (
        again["derived"]["status"] == "broken"
        and again["derived"]["confidence"] > body["derived"]["confidence"]
    )
    assert again["alternatives"]
    feed = client.get("/api/reports?domain=water&limit=5").json()
    assert feed[0]["entity_name"] == "Shule" and feed[0]["note"] in ("handle snapped", None)
    assert client.post("/api/reports", json={"entity_id": "t:shule", "status": "closed"}).status_code == 422
    assert client.post("/api/reports", json={"entity_id": "nope", "status": "broken"}).status_code == 404
    stats = client.get("/api/stats?domain=water").json()
    assert stats["total"] == 5 and stats["reports_24h"] >= 2 and stats["people_affected"] >= 400
    assert client.get("/api/stats?domain=nope").status_code == 404


def test_interactions_and_admin_reset(client: TestClient, seeded: Repository) -> None:
    client.post("/api/sms", data={"From": "+15005550006", "Body": "Shule imeharibika"})
    items = client.get("/api/interactions").json()
    assert items and items[0]["channel"] == "sms" and len(items[0]["sender_hash"]) == 8
    assert client.post("/api/admin/reset").status_code == 403
    r = client.post("/api/admin/reset?mode=live", headers={"X-Admin-Token": "secret"}).json()
    assert r["reset"] == "live" and r["entities"] == 7
    assert client.get("/api/interactions").json() == []
    assert client.get("/api/entities/t:shule").json()["entity"]["properties"]["current_status"] == "unknown"
    r2 = client.post("/api/admin/reset?mode=all", headers={"X-Admin-Token": "secret"}).json()
    assert r2["reset"] == "all" and client.get("/api/health").json()["entities"] == 0
