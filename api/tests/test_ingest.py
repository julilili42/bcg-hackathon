from datetime import UTC, datetime
from pathlib import Path

from reach.ingest import demo_overlay, health, wpdx
from reach.ingest.seed import seed
from reach.settings import REPO_ROOT
from reach.storage.repository import Repository

DATA = REPO_ROOT / "data"


def test_wpdx_snapshot_maps_to_entities() -> None:
    rows = wpdx.load_snapshot(DATA / "wpdx" / "kisarawe.json")
    pairs = wpdx.rows_to_entities(rows)
    assert len(pairs) == 330
    ids = [e.id for e, _ in pairs]
    names = [e.name for e, _ in pairs]
    assert len(set(ids)) == 330 and len(set(names)) == 330
    statuses = [r.status_claimed for _, r in pairs if r]
    assert statuses.count("ok") == 66 and statuses.count("empty") == 145 and statuses.count("broken") == 119
    sample = next(e for e, _ in pairs if e.adm3 == "Marui")
    assert sample.name.startswith("Marui ") and sample.source == "wpdx" and sample.served_population
    assert sample.attributes["water_source"] and sample.attributes["surveyed_on"].startswith("200")


def test_wpdx_status_mapping_edge_cases() -> None:
    assert wpdx.map_status({"status_clean": "Functional, needs repair"}) == "ok"
    assert wpdx.map_status({"status_clean": "Abandoned/Decommissioned"}) == "broken"
    assert wpdx.map_status({"status_clean": "", "status_id": "Yes"}) == "ok"
    assert wpdx.map_status({"status_clean": "Others", "status_id": "Unknown"}) is None
    assert wpdx.generate_names([{"clean_adm3": "A", "water_source_clean": "Protected Well"}]) == ["A Well"]


def test_health_csv_maps_to_entities() -> None:
    pairs = health.rows_to_entities(health.load_csv(DATA / "health" / "kisarawe.csv"))
    assert len(pairs) == 16
    msanga = next(e for e, _ in pairs if e.external_id == "105431-1")
    assert msanga.name == "Msanga Dispensary" and "Zahanati Msanga" in msanga.aliases
    assert all(r is not None and r.status_claimed == "open" for _, r in pairs)


def test_seed_from_real_data_and_overlay(repo: Repository, tmp_path: Path) -> None:
    summary = seed(repo, DATA, reset=True, demo=False)
    assert summary["water_points"] == 330 and summary["clinics"] == 16 and summary["recomputed"] == 346
    stats = repo.stats("water", ["broken", "empty"], 0.3)
    assert stats.total == 330 and stats.verified == 0 and stats.by_status.get("empty") == 145
    first = repo.list_entities("water")[0]
    rows = [
        {"entity_id": first.id, "alias": "Shule", "baseline_status": "ok"},
        {"entity_id": "nope", "alias": "x"},
    ]
    assert demo_overlay.apply_overlay(repo, rows, datetime.now(UTC)) == 1
    renamed = repo.get_entity(first.id)
    assert renamed is not None and renamed.name == "Shule" and first.name in renamed.aliases
    # idempotent re-seed keeps one baseline per entity
    seed(repo, DATA, reset=False, demo=False)
    assert len(repo.reports_for_entity(first.id)) == 2
