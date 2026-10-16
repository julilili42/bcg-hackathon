"""Shared fixtures: isolated SQLite per test, six test entities, the keyword understander, a TestClient."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reach.app import create_app
from reach.brain.keywords import KeywordUnderstander
from reach.core.domains import load_domains
from reach.core.schemas import Entity, Report
from reach.core.service import ReachService
from reach.settings import Settings, get_settings, reset_settings
from reach.storage.db import init_db, make_engine
from reach.storage.repository import Repository

FIXTURES = Path(__file__).parent / "fixtures"
TEST_NUMBER = "+15005550006"  # Twilio magic test number, never a real person

# Fictional test-only points around Kisarawe town. Real data is covered by test_ingest.
TEST_ENTITIES: list[tuple[str, str, str, list[str], float, float, str, int | None]] = [
    ("t:shule", "water", "Shule", ["Kisima cha Shule"], -6.9000, 39.0600, "ok", 400),
    ("t:kanisa", "water", "Kanisa", [], -6.9030, 39.0640, "ok", 250),
    ("t:soko", "water", "Soko", ["Kisima cha Soko"], -6.9100, 39.0700, "broken", 600),
    ("t:bwawa", "water", "Bwawa", [], -6.9200, 39.0800, "empty", 150),
    ("t:market-tap", "water", "Kisarawe Market Tap", [], -6.9050, 39.0580, "ok", 300),
    (
        "t:msanga",
        "health",
        "Msanga Dispensary",
        ["Zahanati Msanga", "Msanga"],
        -7.2843,
        38.7701,
        "open",
        None,
    ),
    ("t:mzenga", "health", "Mzenga Health Centre", ["Kituo cha Afya Mzenga"], -6.9342, 38.7220, "open", None),
]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("TWILIO_VALIDATE", "0")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("REPORTER_SALT", "test-salt")
    monkeypatch.setenv("REACH_AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("REACH_WEB_DIST", str(tmp_path / "no-dist"))
    monkeypatch.setenv("REACH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TTS_PROVIDER", "none")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    monkeypatch.setenv("RATE_LIMIT_MAX", "5")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reset_settings()
    yield get_settings()
    reset_settings()


@pytest.fixture
def repo(env: Settings) -> Repository:
    engine = make_engine(env.database_url)
    init_db(engine)
    return Repository(engine)


@pytest.fixture
def seeded(repo: Repository) -> Repository:
    """Entities with a weak, fresh web baseline (weight 0.3): known state, not yet verified."""
    now = datetime.now(UTC) - timedelta(minutes=10)
    for eid, domain, name, aliases, lat, lon, status, pop in TEST_ENTITIES:
        repo.upsert_entity(
            Entity(
                id=eid,
                domain_id=domain,
                name=name,
                aliases=aliases,
                lat=lat,
                lon=lon,
                adm1="Pwani",
                adm2="Kisarawe",
                adm3="Kisarawe",
                source="demo",
                external_id=eid,
                served_population=pop,
            )
        )
        repo.add_report(
            Report(
                entity_id=eid,
                reporter_hash="seed",
                channel="web",
                lang="en",
                raw_text=None,
                status_claimed=status,
                weight=0.3,
                created_at=now,
            )
        )
    service = ReachService(repo, load_domains(), KeywordUnderstander())
    service.recompute_all()
    return repo


@pytest.fixture
def service(seeded: Repository) -> ReachService:
    return ReachService(seeded, load_domains(), KeywordUnderstander())


@pytest.fixture
def client(env: Settings, seeded: Repository) -> Iterator[TestClient]:
    app = create_app(env)
    with TestClient(app) as tc:
        yield tc


def load_fixture(name: str) -> dict[str, str]:
    data = json.loads((FIXTURES / "twilio" / f"{name}.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return {k: str(v) for k, v in data.items()}
