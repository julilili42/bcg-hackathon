from datetime import UTC, datetime, timedelta

from reach.core.schemas import Entity, Interaction, PendingQuestion, Report
from reach.storage.repository import Repository


def test_upsert_list_bbox_and_aliases(seeded: Repository) -> None:
    water = seeded.list_entities("water")
    assert len(water) == 5
    assert seeded.get_entity("t:shule").aliases == ["Kisima cha Shule"]  # type: ignore[union-attr]
    inside = seeded.list_entities("water", bbox=(-6.905, 39.055, -6.895, 39.065))
    assert {e.id for e in inside} == {"t:shule", "t:kanisa", "t:market-tap"}
    seeded.add_aliases("t:kanisa", ["Church", "Church"])
    assert seeded.get_entity("t:kanisa").aliases == ["Church"]  # type: ignore[union-attr]
    # upsert keeps the id and replaces fields
    e = seeded.get_entity("t:kanisa")
    assert e is not None
    seeded.upsert_entity(e.model_copy(update={"name": "Kanisa Spring"}))
    assert seeded.get_entity("t:kanisa").name == "Kanisa Spring"  # type: ignore[union-attr]
    assert seeded.find_by_external_id("demo", "t:soko") is not None
    assert seeded.count_entities() == 7 and seeded.count_entities("health") == 2


def test_reports_feed_and_stats(seeded: Repository) -> None:
    now = datetime.now(UTC)
    seeded.add_report(
        Report(
            entity_id="t:shule",
            reporter_hash="h1",
            channel="sms",
            lang="sw",
            raw_text="x",
            status_claimed="broken",
            created_at=now,
        )
    )
    seeded.add_report(
        Report(
            entity_id="t:shule",
            reporter_hash="imp",
            channel="import",
            status_claimed="ok",
            created_at=now - timedelta(days=5000),
        )
    )
    feed = seeded.list_reports("water", limit=10)
    assert feed[0].entity_name == "Shule" and feed[0].status_claimed == "broken"
    assert all(r.channel != "import" for r in feed)
    assert len(seeded.reports_for_entity("t:shule")) == 3
    assert seeded.count_reports_by_reporter("h1", now - timedelta(minutes=1)) == 1
    seeded.update_entity_status("t:shule", "broken", 0.7, now)
    stats = seeded.stats("water", ["broken", "empty"], 0.3)
    assert stats.total == 5
    assert stats.by_status["broken"] == 2  # soko + shule
    assert stats.people_affected == 400 + 600 + 150
    assert stats.reports_24h == 6  # five fixture baselines + one sms


def test_interactions_and_reset(seeded: Repository) -> None:
    seeded.log_interaction(
        Interaction(
            channel="sms",
            sender_hash="abc",
            lang="en",
            body="hi",
            reply="hello",
            intent="other",
            entity_id=None,
            latency_ms=12,
            created_at=datetime.now(UTC),
        )
    )
    assert seeded.list_interactions()[0].reply == "hello"
    seeded.clear_live_reports()
    assert seeded.list_interactions() == []
    assert seeded.reports_for_entity("t:shule") == []  # seed baselines were web reports
    seeded.clear_all()
    assert seeded.count_entities() == 0


def test_entity_roundtrip_attributes(repo: Repository) -> None:
    repo.upsert_entity(
        Entity(
            id="x",
            domain_id="water",
            name="X",
            lat=0,
            lon=0,
            source="wpdx",
            external_id="e",
            attributes={"a": 1, "b": "two"},
        )
    )
    e = repo.get_entity("x")
    assert e is not None and e.attributes == {"a": 1, "b": "two"} and e.current_status == "unknown"


def test_pending_question_roundtrip_and_expiry(repo: Repository) -> None:
    now = datetime.now(UTC)
    pending = PendingQuestion(
        key="sms:abc",
        channel="sms",
        domain_id="water",
        lang="sw",
        kind="choose",
        status_claimed="empty",
        candidate_ids=["a", "b"],
        raw_text="marui",
        attempts=1,
        created_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    repo.set_pending(pending)
    got = repo.get_pending("sms:abc", now)
    assert got is not None and got.kind == "choose" and got.candidate_ids == ["a", "b"] and got.attempts == 1
    repo.set_pending(pending.model_copy(update={"kind": "confirm", "candidate_ids": ["a"]}))
    assert repo.get_pending("sms:abc", now).kind == "confirm"  # type: ignore[union-attr]
    assert repo.get_pending("sms:abc", now + timedelta(minutes=11)) is None
    assert repo.get_pending("sms:abc", now) is None  # expired rows are removed on read
    repo.set_pending(pending)
    repo.clear_pending("sms:abc")
    assert repo.get_pending("sms:abc", now) is None
