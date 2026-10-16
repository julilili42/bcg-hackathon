"""The brain without Claude, Qdrant or the real table: `uv run pytest -q`. ponytail: one file, mocks via monkeypatch."""
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from qdrant_client import models

from gateway import db, graph as g, knowledge as kb

REAL = dict(store_facts=kb.store_facts, hybrid_search=kb.hybrid_search, status_history=kb.status_history)  # the fixture mocks these
POINTS = [dict(id=1, name="Zahanati", village="Kigero", lat=-6.7788, lon=38.8615, status="ok", updated="2026-10-16 08:00:00"),
          dict(id=2, name="Mama Nasa", village="Vikuge", lat=-6.7700, lon=38.8600, status="ok", updated="2026-10-16 08:00:00"),
          dict(id=3, name="Rabo", village="Kati", lat=-6.8000, lon=38.9000, status="broken", updated="2026-10-16 08:00:00")]
VILLAGES = [dict(name="Kigero", lat=-6.7790, lon=38.8610), dict(name="Vikuge", lat=-6.7705, lon=38.8605),
            dict(name="Kati", lat=-6.7990, lon=38.8990)]


HAZARDS = []  # rows the graph wrote to the hazard table


@pytest.fixture(autouse=True)
def table(monkeypatch):
    """An in-memory water point table; statuses set by the graph land here."""
    points = [dict(p) for p in POINTS]
    monkeypatch.setattr(db, "waterpoints", lambda: [dict(p) for p in points])
    monkeypatch.setattr(db, "set_status", lambda wp_id, status: next(p for p in points if p["id"] == wp_id).update(status=status))
    monkeypatch.setattr(db, "villages", lambda: [dict(v) for v in VILLAGES])
    monkeypatch.setattr(db, "add_hazard", lambda *a: HAZARDS.append(a))
    HAZARDS.clear()
    monkeypatch.setattr(kb, "store_facts", lambda *a: ["fact-id"])
    monkeypatch.setattr(kb, "hybrid_search", lambda *a: [])
    monkeypatch.setattr(kb, "status_history", lambda *a: [])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return points


def fact(**changes):
    return g.Fact(**{**dict(statement="Zahanati is not working", asset_id="Zahanati", attribute="operational_status", value="broken"), **changes})


def record(key, time, value="working", **extra):
    return dict(point_id=key, source_id=key, asset_id="Zahanati", attribute="operational_status", value=value,
                observed_at=time, verification_status="unverified", **extra)


def use_claude(monkeypatch, interpretation, answer="Dated unverified answer."):
    """Both Claude calls mocked; returns the mock so tests can check which ran."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    model = Mock()
    model.with_structured_output.return_value.invoke.return_value = interpretation
    model.invoke.return_value = SimpleNamespace(content=answer)
    monkeypatch.setattr(g, "llm", lambda: model)
    return model


def test_keywords_report_updates_table_and_names_nearest(table):
    r = g.handle_turn("the Zahanati well is broken", "u", "t", "en")
    assert r["intent"] == "report" and r["stored_fact_ids"] == ["fact-id"]
    assert table[0]["status"] == "broken"
    assert r["answer"].startswith("Thank you. Zahanati is recorded as broken. From Zahanati, the nearest working water point is Mama Nasa, ")
    assert g.handle_turn("Zahanati imeharibika", "u", "t")["lang"] == "sw"
    assert "kaputt" in g.handle_turn("Rabo ist kaputt", "u", "t")["answer"]


def test_keywords_query_and_unclear():
    r = g.handle_turn("Is Rabo working?", "u", "t", "en")
    assert r["intent"] == "query" and r["stored_fact_ids"] == []
    assert r["answer"].startswith("Rabo is broken. From Rabo, the nearest working water point is")
    assert g.handle_turn("blah", "u", "t", "en")["answer"] == g.T["en"]["unknown"]
    assert g.handle_turn("", "u", "t", "sw")["answer"] == g.T["sw"]["unknown"]


def test_claude_both_stores_before_search_and_answers_in_callers_language(monkeypatch):
    calls = []
    monkeypatch.setattr(kb, "store_facts", lambda *a: calls.append("store") or ["fact-id"])
    monkeypatch.setattr(kb, "hybrid_search", lambda q, *a: calls.append(("search", q)) or [record("old", "2026-10-15T08:00:00Z")])
    model = use_claude(monkeypatch, g.Interpretation(intent="both", facts=[fact()], query="Is Mama Nasa working?",
                                                     query_asset_id="Mama Nasa", query_kind="current_status", lang="en"))
    r = g.handle_turn("Zahanati imeharibika. Mama Nasa inafanya kazi?", "u", "t", "sw")
    assert calls == ["store", ("search", "Is Mama Nasa working?")]
    assert r["lang"] == "sw" and r["answer"].startswith("Asante. Zahanati imeandikwa kama imeharibika. Dated unverified answer.")
    assert "Swahili" in model.invoke.call_args.args[0][0][1]


def test_claude_failure_falls_back_to_keywords(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(g, "llm", lambda: (_ for _ in ()).throw(RuntimeError("api down")))
    assert g.handle_turn("Zahanati is empty", "u", "t", "en")["answer"].startswith("Thank you. Zahanati is recorded as empty.")


def test_query_without_evidence_answers_from_table(monkeypatch):
    model = use_claude(monkeypatch, g.Interpretation(intent="query", query="Is Zahanati working?", query_asset_id="Zahanati", query_kind="current_status"))
    assert g.handle_turn("Is Zahanati working?", "u", "t", "en")["answer"] == "Zahanati is working."
    model.invoke.assert_not_called()


def test_safety_never_inferred_from_operation(monkeypatch):
    model = use_claude(monkeypatch, g.Interpretation(intent="query", query="Is the water safe?", query_asset_id="Zahanati", query_kind="safety"))
    monkeypatch.setattr(kb, "hybrid_search", lambda *a: [record("r", "2026-10-16T08:00:00Z")])
    assert g.handle_turn("Is Zahanati water safe?", "u", "t", "en")["answer"] == g.T["en"]["safety"]
    model.invoke.assert_not_called()


def test_knowledge_store_down_still_answers(monkeypatch, table):
    monkeypatch.setattr(kb, "store_facts", lambda *a: (_ for _ in ()).throw(ConnectionError()))
    monkeypatch.setattr(kb, "hybrid_search", lambda *a: (_ for _ in ()).throw(ConnectionError()))
    r = g.handle_turn("Zahanati is broken", "u", "t", "en")
    assert r["stored_fact_ids"] == [] and table[0]["status"] == "broken" and "Mama Nasa" in r["answer"]
    assert g.handle_turn("Is Zahanati working?", "u", "t", "en")["answer"].startswith("Zahanati is broken.")


def test_interpretation_consistency_and_registry():
    with pytest.raises(ValueError):
        g.Interpretation(intent="query", facts=[fact()], query="Working?")
    i = g.Interpretation(intent="report", facts=[fact(asset_id="Nowhere")])
    assert i.facts[0].asset_id is None and g.point(i) is None
    i = g.Interpretation(intent="query", query="?", query_asset_id="Rabo")
    assert i.query_village == "Kati" and g.point(i) == "Rabo"


def test_keywords_hazard_on_the_way_is_stored_anonymously_and_names_another_point(table):
    r = g.handle_turn("Men harass women on the way from Kigero to Zahanati", "caller-abc", "t", "en")
    assert r["intent"] == "report" and r["hazard"] and (r["village"], r["point"]) == ("Kigero", "Zahanati")
    assert HAZARDS == [("Kigero", "Zahanati", "harassment", "Men harass women on the way from Kigero to Zahanati", "caller-abc")]
    assert table[0]["status"] == "ok"  # a danger on the way is not a broken pump
    assert r["answer"] == ("Thank you. Your safety report about the way from Kigero to Zahanati is recorded. Your name and number "
                           "are not shown. From Kigero, another working water point is Mama Nasa, about 15 minutes on foot.")


def test_hazard_resolves_the_missing_end_of_the_route():
    near = g.Interpretation(intent="report", facts=[fact(asset_id=None, village="Kati", attribute="route_hazard", value="snakes")])
    assert (near.facts[0].asset_id, near.facts[0].value) == ("Rabo", "other")  # nearest water point; unknown kinds become other
    served = g.Interpretation(intent="report", facts=[fact(village="Atlantis", attribute="route_hazard", value="animals")])
    assert g.place(served) == ("Kigero", "Zahanati") and g.hazard(served)


def test_village_alone_is_a_place_to_show():
    r = g.handle_turn("Kati imefungwa?", "u", "t", "sw")  # "is it blocked?": a question, the map still goes to Kati
    assert r["intent"] == "query" and (r["village"], r["point"]) == ("Kati", None) and not r["hazard"]
    assert r["answer"] == "Kutoka Kati, kisima cha karibu kinachofanya kazi ni Zahanati, takriban dakika 70 kwa miguu."
    i = g.understand("Le chemin de Vikuge est bloqué, danger", "fr")
    assert i.facts[0].attribute == "route_hazard" and g.place(i) == ("Vikuge", "Mama Nasa") and i.lang == "fr"


def test_french_status_report():
    r = g.handle_turn("La source Zahanati est en panne", "u", "t")
    assert r["lang"] == "fr" and r["answer"].startswith("Merci. Zahanati est enregistré comme en panne. Depuis Zahanati, ")


@pytest.mark.parametrize("timestamp,expected", [("2026-10-16T14:00:00", None), ("2026-10-16", None), ("this afternoon", None),
                                                (None, None), ("2026-10-16T17:00:00+03:00", "2026-10-16T14:00:00+00:00")])
def test_uncertain_observation_time_preserves_report(timestamp, expected):
    f = fact(observed_at=timestamp)
    assert f.observed_at == expected and "not working" in f.statement
    evidence = kb.resolve_evidence([record("new", expected, reported_at="2026-10-16T14:30:00Z")], True)
    assert evidence[0]["time_basis"] == ("observed_at" if expected else "report/document time")


def test_recency_conflicts_and_private_provenance():
    old = record("old", "2023-01-01T00:00:00Z", ingested_at="2026-10-16T15:00:00Z", user_id="caller-x")
    broken = record("broken", "2026-10-16T08:00:00Z", "broken")
    repaired = record("repaired", "2026-10-16T14:00:00Z")
    result = kb.resolve_evidence([old, broken, repaired], True, "repaired")
    assert [p["source_id"] for p in result] == ["repaired", "broken"]
    assert all(p["conflict"] for p in result) and result[0]["just_reported"] and result[0]["latest_for_asset"]
    assert len(kb.resolve_evidence([old, broken, repaired], False)) == 3
    assert "user_id" not in kb.resolve_evidence([old])[0]


def test_hybrid_filters_rrf_and_exact_history(monkeypatch):
    c = Mock()
    c.query_points.return_value.points = []
    c.scroll.return_value = ([SimpleNamespace(id="new", payload=record("new", "2026-10-16T08:00:00Z", "broken"))], None)
    monkeypatch.setattr(kb, "client", lambda: c)
    monkeypatch.setattr(kb, "initialize", lambda: True)
    monkeypatch.setattr(kb, "dense", lambda text: [0.0] * 384)
    assert REAL["hybrid_search"]("working?", "Zahanati", "Kigero") == []
    kwargs = c.query_points.call_args.kwargs
    assert [p.using for p in kwargs["prefetch"]] == ["dense", "bm25"] and kwargs["query"].fusion == models.Fusion.RRF
    for p in kwargs["prefetch"]:
        assert {f.key: f.match.value for f in p.filter.must} == {"asset_id": "Zahanati", "village": "Kigero"}
    assert kb.resolve_evidence(REAL["status_history"]("Zahanati"), True)[0]["value"] == "broken"
    assert c.scroll.call_args.kwargs["limit"] == 100


def test_idempotent_fact_points(monkeypatch):
    points = {}
    c = Mock()
    c.upsert.side_effect = lambda *a, **kw: points.update({p.id: p for p in kw["points"]})
    monkeypatch.setattr(kb, "client", lambda: c)
    monkeypatch.setattr(kb, "initialize", lambda: True)
    monkeypatch.setattr(kb, "dense", lambda text: [0.0] * 384)
    for _ in range(2):
        REAL["store_facts"]([fact()], "original", "caller-x", "same-turn", "2026-10-16T08:00:00Z")
    assert len(points) == 1
    p = next(iter(points.values()))
    assert p.payload["source_text"] == "original" and p.payload["verification_status"] == "unverified"


@pytest.mark.skipif(os.getenv("RUN_QDRANT_SMOKE") != "1", reason="needs a running Qdrant and the embedding model")
def test_real_qdrant_roundtrip():
    ids = REAL["store_facts"]([fact()], "smoke report", "caller-smoke", "smoke-turn", "2026-10-16T08:00:00Z")
    try:
        assert any(p["source_id"] == "smoke-turn" for p in REAL["status_history"]("Zahanati"))
        assert REAL["hybrid_search"]("Is Zahanati working?", "Zahanati", "Kigero")
    finally:
        kb.client().delete(kb.COLLECTION, models.PointIdsList(points=ids), wait=True)
