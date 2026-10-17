import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from qdrant_client import models

import graph as g
import knowledge as kb
from app import app


def fact(**changes):
    return g.Fact(statement="Alero clinic pump is not working", asset_id="alero_clinic_pump",
                  attribute="operational_status", value="broken", **changes)


def record(key, time, value="working", **extra):
    return dict(point_id=key, source_id=key, asset_id="alero_clinic_pump",
                attribute="operational_status", value=value, observed_at=time,
                verification_status="unverified", **extra)


def invoke(monkeypatch, interpretation):
    calls = []
    model = Mock()
    model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=interpretation)
    model.ainvoke = AsyncMock(return_value=SimpleNamespace(content="Dated unverified demo answer."))
    monkeypatch.setattr(g, "llm", lambda: model)
    monkeypatch.setattr(kb, "store_facts", lambda *args: calls.append("store") or ["fact-id"])
    monkeypatch.setattr(kb, "hybrid_search", lambda *args: calls.append(("search", args[0])) or [record("old", "2026-10-15T08:00:00Z")])
    monkeypatch.setattr(kb, "status_history", lambda *args: [])
    result = asyncio.run(g.handle_turn("resident message", "demo-a", "turn-a", "2026-10-16T08:30:00Z"))
    return result, calls, model


def test_question_only_does_not_store(monkeypatch):
    result, calls, _ = invoke(monkeypatch, g.Interpretation(intent="query", query="Is the clinic pump working?"))
    assert result["stored_fact_ids"] == []
    assert calls == [("search", "Is the clinic pump working?")]


def test_report_only_and_unclear(monkeypatch):
    result, calls, model = invoke(monkeypatch, g.Interpretation(intent="report", facts=[fact()]))
    assert calls == ["store"] and result["sources"] == []
    assert "recorded" in result["answer"]
    model.ainvoke.assert_not_called()
    result, calls, _ = invoke(monkeypatch, g.Interpretation(intent="unclear"))
    assert calls == [] and "Which water point" in result["answer"]


def test_both_stores_before_extracted_query(monkeypatch):
    result, calls, _ = invoke(monkeypatch, g.Interpretation(intent="both", facts=[fact()], query="Is the school borehole working?"))
    assert calls == ["store", ("search", "Is the school borehole working?")]
    assert result["intent"] == "both"
    with pytest.raises(ValueError):
        g.Interpretation(intent="query", facts=[fact()], query="Working?")


def test_idempotent_fact_points_and_private_provenance(monkeypatch):
    points = {}
    c = Mock()
    c.upsert.side_effect = lambda *args, **kwargs: points.update({p.id: p for p in kwargs["points"]})
    monkeypatch.setattr(kb, "client", lambda: c)
    monkeypatch.setattr(kb, "dense", lambda text: [0.0] * 384)
    for _ in range(2):
        kb.store_facts([fact()], "original message", "private-user", "same-turn", "2026-10-16T08:00:00Z")
    assert len(points) == 1
    p = next(iter(points.values()))
    assert p.payload["source_text"] == "original message"
    assert p.payload["verification_status"] == "unverified"
    assert "user_id" not in kb.resolve_evidence([{**p.payload, "point_id": str(p.id)}])[0]


def test_hybrid_filters_rrf_and_exact_history(monkeypatch):
    c = Mock()
    c.query_points.return_value.points = []
    c.scroll.return_value = ([SimpleNamespace(id="new", payload=record("new", "2026-10-16T08:00:00Z", "broken"))], None)
    monkeypatch.setattr(kb, "client", lambda: c)
    monkeypatch.setattr(kb, "dense", lambda text: [0.0] * 384)
    assert kb.hybrid_search("working?", "alero_clinic_pump", "Alero") == []
    kwargs = c.query_points.call_args.kwargs
    assert [p.using for p in kwargs["prefetch"]] == ["dense", "bm25"]
    assert kwargs["query"].fusion == models.Fusion.RRF
    for p in kwargs["prefetch"]:
        assert {f.key: f.match.value for f in p.filter.must} == {"asset_id": "alero_clinic_pump", "village": "Alero"}
    result = kb.resolve_evidence(kb.status_history("alero_clinic_pump"), True)
    assert result[0]["value"] == "broken"  # found despite absence from fused top 12
    assert c.scroll.call_args.kwargs["limit"] == 100


def test_recency_conflicts_and_stable_documents():
    old = record("old", "2023-01-01T00:00:00Z", ingested_at="2026-10-16T15:00:00Z")
    broken = record("broken", "2026-10-16T08:00:00Z", "broken")
    repaired = record("repaired", "2026-10-16T14:00:00Z")
    records = [old, broken, repaired]
    result = kb.resolve_evidence(records, True, "repaired")
    assert [p["source_id"] for p in result] == ["repaired", "broken"]
    assert all(p["conflict"] and p["verification_status"] == "unverified" for p in result)
    assert result[0]["just_reported"] and len(records) == 3
    assert len(kb.resolve_evidence(records, False)) == 3


@pytest.mark.parametrize("timestamp,expected", [
    ("2026-10-16T14:00:00", None),
    ("2026-10-16", None),
    ("this afternoon", None),
    (None, None),
    ("2026-10-16T17:00:00+03:00", "2026-10-16T14:00:00+00:00"),
])
def test_uncertain_observation_time_preserves_report(timestamp, expected):
    interpretation = g.Interpretation.model_validate(dict(intent="both",
        facts=[dict(statement="I saw the Alero clinic pump repaired this afternoon.",
                    asset_id="alero_clinic_pump", observed_at=timestamp)],
        query="Is the Alero clinic pump usable now?"))
    assert interpretation.facts[0].observed_at == expected
    assert "this afternoon" in interpretation.facts[0].statement
    report = record("new", expected, reported_at="2026-10-16T14:30:00Z")
    evidence = kb.resolve_evidence([report], True)
    assert evidence[0]["time_basis"] == ("observed_at" if expected else "report/document time")


def test_api_clock_missing_information_and_safety(monkeypatch):
    import app as api
    monkeypatch.setattr(api, "initialize", lambda: None)
    mocked = AsyncMock(return_value={"answer": "ok"})
    monkeypatch.setattr(api, "handle_turn", mocked)
    with TestClient(app) as client:
        response = client.post("/interact", json={"message": "working?", "turn_id": "retry-me"})
        assert response.status_code == 200
        assert mocked.call_args.args[2] == "retry-me"
        assert client.post("/interact", json={"message": "x", "received_at": "1900-01-01"}).status_code == 422
    model = Mock()
    model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=g.Interpretation(intent="query", query="Is water safe?", query_kind="safety"))
    model.ainvoke = AsyncMock()
    monkeypatch.setattr(g, "llm", lambda: model)
    monkeypatch.setattr(kb, "hybrid_search", lambda *args: [])
    result = asyncio.run(g.handle_turn("Is water safe?", "u", "t", "2026-10-16T08:00:00Z"))
    assert "can't confirm the water is safe" in result["answer"]
    model.ainvoke.assert_not_called()
    state = dict(interpretation=g.Interpretation(intent="query", query="Working?"),
                 stored_ids=[], retrieved=[], turn_id="t", received_at="2026-10-16T08:00:00Z")
    assert "don't have a recent report" in asyncio.run(g.respond(state))["answer"]


def test_configuration_failure_is_actionable(monkeypatch):
    import app as api
    for key in ("ANTHROPIC_API_KEY",):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(g.ConfigurationError, match="ANTHROPIC_API_KEY") as error:
        g.check_configuration()
    monkeypatch.setattr(api, "initialize", lambda: None)
    monkeypatch.setattr(api, "handle_turn", AsyncMock(side_effect=error.value))
    with TestClient(app) as client:
        response = client.post("/interact", json={"message": "Working?"})
    assert response.status_code == 503
    assert "Anthropic is not configured" in response.json()["detail"]["message"]
    assert ".env" in response.json()["detail"]["message"]


@pytest.mark.parametrize("configured,expected", [("", "claude-sonnet-4-6"), ("custom-model", "custom-model")])
def test_anthropic_configuration(monkeypatch, configured, expected):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", configured)
    constructor = Mock()
    monkeypatch.setattr(g, "ChatAnthropic", constructor)
    g.llm.cache_clear()
    try:
        g.llm()
        assert constructor.call_args.kwargs["model"] == expected
        assert constructor.call_args.kwargs["api_key"] == "synthetic-test-key"
        assert "azure_deployment" not in constructor.call_args.kwargs
    finally:
        g.llm.cache_clear()


def test_anthropic_answer_content_blocks(monkeypatch):
    model = Mock()
    model.ainvoke = AsyncMock(return_value=SimpleNamespace(content=[
        {"type": "thinking", "thinking": "internal reasoning"},
        {"type": "text", "text": "An unverified community report says "},
        {"type": "text", "text": "the Alero clinic pump is broken."},
    ]))
    monkeypatch.setattr(g, "llm", lambda: model)
    result = asyncio.run(g.respond(dict(
        interpretation=g.Interpretation(intent="query", query="Is the clinic pump working?"),
        stored_ids=[], retrieved=[record("report", "2026-10-16T08:00:00Z", "broken")],
        turn_id="reader", received_at="2026-10-16T09:00:00Z")))
    assert result["answer"] == "An unverified community report says the Alero clinic pump is broken."


@pytest.mark.skipif(os.getenv("RUN_QDRANT_SMOKE") != "1", reason="requires real Qdrant + model download")
def test_real_qdrant_smoke(monkeypatch):
    from seed import seed
    seed()
    question = "Is the Alero school borehole working?"
    filt = kb.payload_filter("alero_school_borehole", "Alero")
    for using, query in [("dense", kb.dense(question)),
                         ("bm25", models.Document(text=question, model=kb.BM25_MODEL))]:
        hits = kb.client().query_points(kb.COLLECTION, query=query, using=using, query_filter=filt, with_payload=True).points
        assert hits and all(p.payload["asset_id"] == "alero_school_borehole" for p in hits)
    hits = kb.hybrid_search(question, "alero_school_borehole", "Alero")
    assert any(p.get("reported_at") and p["source_id"] for p in hits)
    before = kb.client().count(kb.COLLECTION, exact=True).count
    ids = kb.store_facts([fact()], "SYNTHETIC smoke report", "demo-smoke", "smoke-turn", "2026-10-16T08:00:00Z")
    try:
        kb.store_facts([fact()], "SYNTHETIC smoke report", "demo-smoke", "smoke-turn", "2026-10-16T08:00:00Z")
        assert kb.client().count(kb.COLLECTION, exact=True).count == before + 1
        assert any(p["source_id"] == "smoke-turn" for p in kb.status_history("alero_clinic_pump"))
    finally:
        kb.client().delete(kb.COLLECTION, models.PointIdsList(points=ids), wait=True)
    # Exercise the actual graph and database; only the credential-bound chat model is mocked.
    model = Mock()
    model.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=[
        g.Interpretation(intent="both", facts=[fact()], query="Is the Alero school borehole working?",
                         query_asset_id="alero_school_borehole", query_kind="current_status"),
        g.Interpretation(intent="query", query="Is the Alero clinic pump working?",
                         query_asset_id="alero_clinic_pump", query_kind="current_status")])
    model.ainvoke = AsyncMock(return_value=SimpleNamespace(content="Synthetic unverified report."))
    monkeypatch.setattr(g, "llm", lambda: model)
    # A previously rehearsed demo can already contain later October 16 reports.
    # Use the trusted current clock so this temporary observation is the latest.
    smoke_time = kb.utcnow()
    first = asyncio.run(g.handle_turn("SYNTHETIC clinic report and school question", "demo-a", "smoke-mixed", smoke_time))
    try:
        second = asyncio.run(g.handle_turn("Is the Alero clinic pump working?", "demo-b", "smoke-reader", smoke_time))
        assert first["intent"] == "both" and first["stored_fact_ids"]
        assert all(p["asset_id"] == "alero_school_borehole" for p in first["sources"])
        assert any(p["source_id"] == "smoke-mixed" for p in second["sources"])
        assert not second["stored_fact_ids"]
    finally:
        kb.client().delete(kb.COLLECTION, models.PointIdsList(points=first["stored_fact_ids"]), wait=True)


def test_registered_uuid_and_legacy_document_ids_share_location_filter(monkeypatch):
    c = Mock()
    c.query_points.return_value.points = []
    monkeypatch.setattr(kb, "client", lambda: c)
    monkeypatch.setattr(kb, "dense", lambda text: [0.0] * 384)
    ids = ["00000000-0000-0000-0000-000000000001", "alero_school_borehole"]
    kb.hybrid_search("school history", ids, "Alero")
    for prefetch in c.query_points.call_args.kwargs["prefetch"]:
        fields = {condition.key: condition.match for condition in prefetch.filter.must}
        assert fields["asset_id"].any == ids
        assert fields["village"].value == "Alero"


def test_graph_searches_registered_aliases_without_mutating_documents(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "synthetic-test-url")
    pipe = dict(id="00000000-0000-0000-0000-000000000001", village="Alero",
                aliases=["alero_school_borehole", "Alero School pipe"])
    monkeypatch.setattr(g, "current_sql_evidence", lambda *args: ([], "", pipe))
    search = Mock(return_value=[])
    monkeypatch.setattr(kb, "hybrid_search", search)
    asyncio.run(g.retrieve_if_needed(dict(interpretation=g.Interpretation(intent="query",
        query="What was reported about Alero school borehole before?", query_kind="history"),
        turn_id="read-only", received_at="2026-10-17T12:00:00Z")))
    search.assert_called_once_with("What was reported about Alero school borehole before?",
        [pipe["id"], "alero_school_borehole"], "Alero")
