"""Real PostgreSQL tests in a temporary schema; model/index failures are controlled."""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

import graph as g
import infrastructure as db
import knowledge as kb
from seed_infrastructure import seed


@pytest.fixture
def registry(monkeypatch):
    if os.getenv("RUN_POSTGRES_SMOKE") != "1":
        pytest.skip("set RUN_POSTGRES_SMOKE=1 for real PostgreSQL integration")
    url = os.getenv("TEST_DATABASE_URL", db.DEFAULT_URL)
    schema = "waterline_test_" + uuid4().hex
    with psycopg.connect(url) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(db, "connect", lambda: psycopg.connect(url, row_factory=dict_row,
                         options=f"-c search_path={schema}", connect_timeout=5))
    seed()
    yield schema
    with psycopg.connect(url) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def observation(name="Alero school borehole", value="broken", observed="2026-10-16T08:00:00Z", **kwargs):
    return g.Fact(statement=f"SYNTHETIC {name} reported {value}", asset_name=name,
                  village="Alero", attribute="operational_status", value=value, observed_at=observed, **kwargs)


def save(fact, turn="test-turn", received="2026-10-16T12:00:00Z"):
    return db.save_pipe_report(fact, fact.statement, "demo-resident", turn, 0, received)


def test_failure_repair_history_and_idempotency(registry, monkeypatch):
    writes = []
    monkeypatch.setattr(kb, "ingest", lambda payload, point_id: writes.append((point_id, payload)))
    failed = db.store_reports([observation()], "SYNTHETIC school broken", "demo-a", "failure", "2026-10-16T09:00:00Z")[0]
    assert failed["applied_to_current_status"] and failed["qdrant_indexed"]
    assert db.get_pipe_by_id(failed["pipe_id"])["status"] == "broken"
    fixed = save(observation(value="operational", observed="2026-10-16T10:00:00Z"), "repair")
    pipe = db.get_pipe_by_id(failed["pipe_id"])
    assert pipe["status"] == "operational" and pipe["latest_report_id"] == fixed["id"]
    assert pipe["needs_verification"]
    history = db.get_pipe_history(pipe["id"])
    assert {r["reported_status"] for r in history} == {"operational", "broken"}
    retry = save(observation(value="operational", observed="2026-10-16T10:00:00Z"), "repair")
    assert retry["id"] == fixed["id"] and len(db.get_pipe_history(pipe["id"])) == len(history)
    assert writes[0][0] == str(failed["id"])
    assert writes[0][1]["source_text"] == "SYNTHETIC school broken"


def test_old_ambiguous_and_future_times_do_not_overwrite(registry):
    recent = save(observation(value="operational", observed="2026-10-16T10:00:00Z"), "new")
    old = save(observation(observed="2026-10-09T08:00:00Z"), "old")
    ambiguous = save(observation(observed=None), "vague")
    future = save(observation(observed="2027-01-01T00:00:00Z"), "future")
    assert not any(r["applied_to_current_status"] for r in [old, ambiguous, future])
    assert db.get_pipe_by_id(recent["pipe_id"])["latest_report_id"] == recent["id"]
    assert len(db.get_pipe_history(recent["pipe_id"])) == 5
    present = save(observation(observed=None, time_basis="present"), "present")
    assert present["applied_to_current_status"]
    assert present["observed_at"] == db.timestamp("2026-10-16T12:00:00Z")


def test_entity_resolution_and_unmatched_report(registry):
    assert db.resolve_pipe("Alero School pipe")["status"] == "matched"
    assert db.resolve_pipe("Alero Market Water Point")["pipe"]["name"] == "Alero market tap"
    assert db.resolve_pipe("Alero schol borehole", "Alero")["status"] == "matched"
    result = db.resolve_pipe("the pipe near the school")
    assert result["status"] == "ambiguous" and len(result["candidates"]) >= 3
    assert db.resolve_pipe("nonexistent pipe")["status"] == "unmatched"
    assert db.resolve_pipe("school", "Kito")["pipe"]["village"] == "Kito"
    arbitrary = observation().model_copy(update={"asset_name": "school", "village": None, "asset_id": str(uuid4())})
    report = save(arbitrary)
    assert report["pipe_id"] is None and report["resolution_status"] == "ambiguous"
    assert not report["applied_to_current_status"]


def test_index_failure_and_recovery(registry, monkeypatch):
    monkeypatch.setattr(kb, "ingest", Mock(side_effect=RuntimeError("synthetic outage")))
    report = db.store_reports([observation()], "Synthetic broken report", "demo-a", "outage", "2026-10-16T12:00:00Z")[0]
    assert not report["qdrant_indexed"]
    assert db.get_pipe_by_id(report["pipe_id"])["status"] == "broken"
    writes = Mock()
    monkeypatch.setattr(kb, "ingest", writes)
    indexed, failed = db.reindex()
    assert indexed == 13 and failed == 0  # 12 fictional seed observations + new report
    assert db.reindex() == (0, 0)
    assert any(call.kwargs["point_id"] == str(report["id"]) for call in writes.call_args_list)


def run_graph(monkeypatch, interpretation, message="Synthetic resident message"):
    model = Mock()
    model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=interpretation)
    model.ainvoke = AsyncMock(return_value=SimpleNamespace(content="Latest unverified SQL reports."))
    monkeypatch.setattr(g, "llm", lambda: model)
    result = asyncio.run(g.handle_turn(message, "demo-a", str(uuid4()), "2026-10-16T12:00:00Z"))
    return result, model


def test_mixed_report_before_retrieval_and_sql_alternatives(registry, monkeypatch):
    monkeypatch.setattr(kb, "ingest", Mock())
    def search(*args):
        assert db.resolve_pipe("Alero Market Water Point")["pipe"]["status"] == "broken"
        return []
    monkeypatch.setattr(kb, "hybrid_search", search)
    report = observation("Alero Market Water Point")
    result, model = run_graph(monkeypatch, g.Interpretation(intent="both", facts=[report],
        query="Which other water points in Alero are working?", query_village="Alero", query_kind="current_status"))
    assert result["reports"][0]["applied_to_current_status"]
    operational = [p for p in result["sources"] if p["value"] == "operational"]
    assert operational and all("market" not in p["asset_name"].lower() for p in operational)
    assert all(p["authoritative_current_status"] and p["verification_status"] == "unverified" for p in result["sources"])
    assert "user_id" not in model.ainvoke.call_args.args[0][1][1]


def test_query_only_sql_over_stale_qdrant_and_no_writes(registry, monkeypatch):
    saved = save(observation(), "failure")
    with db.connect() as conn:
        before = conn.execute("SELECT count(*) AS n FROM pipe_reports").fetchone()["n"]
    monkeypatch.setattr(kb, "hybrid_search", lambda *args: [dict(point_id="old-qdrant", asset_id=str(saved["pipe_id"]),
        attribute="operational_status", value="working", observed_at="2026-10-10T08:00:00Z", source_id="old")])
    result, _ = run_graph(monkeypatch, g.Interpretation(intent="query", query="Is the Alero school borehole working?",
        query_asset_name="Alero School Borehole", query_village="Alero", query_kind="current_status"))
    assert not result["stored_fact_ids"]
    assert len(result["sources"]) == 1 and result["sources"][0]["value"] == "broken"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM pipe_reports").fetchone()["n"] == before


def test_ambiguous_report_asks_and_preserves_evidence(registry, monkeypatch):
    monkeypatch.setattr(kb, "ingest", Mock())
    fact = observation().model_copy(update={"asset_name": "pipe near the school", "village": None})
    result, model = run_graph(monkeypatch, g.Interpretation(intent="report", facts=[fact]))
    assert "Which water point" in result["answer"] and "Kito School" in result["answer"]
    assert result["reports"][0]["resolution_status"] == "ambiguous"
    assert result["reports"][0]["qdrant_indexed"]
    assert not result["reports"][0]["applied_to_current_status"]
    model.ainvoke.assert_not_called()


def test_seed_idempotence_and_dashboard(registry):
    from streamlit.testing.v1 import AppTest
    seed()
    assert len(db.get_pipes()) == 12
    assert sum(len(db.get_pipe_history(p["id"])) for p in db.get_pipes()) == 12
    app = AppTest.from_file("../dashboard.py").run(timeout=20)
    assert not app.exception
    assert [m.value for m in app.metric] == ["12", "5", "3", "12"]
    save(observation(), "dashboard-change")
    app.run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["12", "4", "4", "12"]


@pytest.mark.skipif(os.getenv("RUN_QDRANT_SMOKE") != "1", reason="requires real Qdrant")
def test_real_graph_postgres_and_hybrid_qdrant(registry, monkeypatch):
    from qdrant_client import models
    monkeypatch.setattr(kb, "COLLECTION", "waterline_smoke_" + uuid4().hex)
    kb.initialize()
    try:
        result, _ = run_graph(monkeypatch, g.Interpretation(intent="both", facts=[observation()],
            query="Is the Alero school borehole working?", query_asset_name="Alero School Borehole",
            query_village="Alero", query_kind="current_status"))
        assert result["reports"][0]["qdrant_indexed"]
        report_id = result["reports"][0]["id"]
        pipe_id = result["reports"][0]["pipe_id"]
        for using, query in [("dense", kb.dense("school borehole broken")),
                             ("bm25", models.Document(text="school borehole broken", model=kb.BM25_MODEL))]:
            hits = kb.client().query_points(kb.COLLECTION, query=query, using=using,
                query_filter=kb.payload_filter(pipe_id, "Alero"), with_payload=True).points
            assert any(str(p.id) == report_id for p in hits)
        assert kb.hybrid_search("school borehole broken", pipe_id, "Alero")[0]["report_id"] == report_id
        assert result["sources"][0]["value"] == "broken"
        assert db.get_pipe_by_id(pipe_id)["status"] == "broken"
    finally:
        kb.client().delete_collection(kb.COLLECTION)


def test_showcase_seed_is_idempotent_and_preserves_history(registry, monkeypatch):
    import seed_showcase as showcase
    documents = {}
    monkeypatch.setattr(kb, "initialize", lambda: None)
    def ingest(payload, point_id=None):
        key = point_id or payload["source_id"]
        documents[key] = payload
        return key
    monkeypatch.setattr(kb, "ingest", ingest)
    first = showcase.seed("test-showcase")
    second = showcase.seed("test-showcase")
    assert first == second
    assert len(first["report_ids"]) == len(set(first["report_ids"])) == 6
    assert len(first["document_ids"]) == 6
    for key, expected in showcase.BASELINE:
        pipe = db.resolve_pipe(key)["pipe"]
        assert pipe["status"] == expected and pipe["needs_verification"]
    clinic = db.resolve_pipe("alero_clinic_pump")["pipe"]
    history = db.get_pipe_history(clinic["id"])
    assert len(history) == 4  # Original registry observation plus three showcase observations.
    assert any(r["reported_status"] == "broken" for r in history)
    notice = documents["test-showcase:clinic-repair-plan"]
    assert notice["asset_id"] == str(clinic["id"])
    assert "not a completed repair" in notice["text"]
    assert all(doc["verification_status"] == "unverified" for doc in documents.values())


@pytest.mark.skipif(os.getenv("RUN_LIVE_LLM") != "1", reason="requires configured Anthropic and Qdrant")
def test_live_showcase_three_turns(registry, monkeypatch):
    import seed_showcase as showcase
    monkeypatch.setattr(kb, "COLLECTION", "waterline_showcase_test_" + uuid4().hex)
    try:
        showcase.seed("isolated-showcase")
        results = []
        for index, prompt in enumerate(showcase.PROMPTS):
            result = asyncio.run(g.handle_turn(prompt, "demo-b" if index == 1 else "demo-a",
                str(uuid4()), kb.utcnow()))
            results.append(result)
            print(f"Showcase turn {index + 1}: {result['answer']}")
            assert not any(char.isdigit() for char in result["answer"])
            assert len(result["answer"].split()) <= 80
            expected = "operational" if index == 2 else "broken"
            assert db.resolve_pipe("alero_clinic_pump")["pipe"]["status"] == expected
        assert [r["intent"] for r in results] == ["both", "query", "both"]
        assert not results[1]["stored_fact_ids"]
        assert any(s.get("source_id") == "isolated-showcase:clinic-repair-plan" for s in results[1]["sources"])
        assert any(s.get("value") == "operational" and "school" in str(s).lower() for s in results[0]["sources"])
        history = db.get_pipe_history(db.resolve_pipe("alero_clinic_pump")["pipe"]["id"])
        assert len(history) >= 6
    finally:
        if kb.client().collection_exists(kb.COLLECTION):
            kb.client().delete_collection(kb.COLLECTION)


@pytest.mark.skipif(os.getenv("RUN_LIVE_LLM") != "1", reason="requires configured Anthropic and Qdrant")
def test_live_followups_use_same_graph_and_preserve_provenance(registry, monkeypatch):
    import seed_showcase as showcase
    monkeypatch.setattr(kb, "COLLECTION", "waterline_context_test_" + uuid4().hex)
    context = [{"role": "assistant", "content":
        "WaterLine AI here. The Alero school borehole was reported working, unverified. How can I help?"}]
    try:
        showcase.seed("isolated-call-context")
        with db.connect() as conn:
            before = conn.execute("SELECT count(*) AS n FROM pipe_reports").fetchone()["n"]
        messages = ["It is broken right now. Where else can I go?",
                    "The water point you just suggested is also broken.",
                    "Can you show me the route there?"]
        results = []
        for message in messages:
            result = asyncio.run(g.handle_turn(message, "demo-call-context", str(uuid4()), kb.utcnow(), context=context))
            results.append(result)
            context.extend([{"role": "user", "content": message}, {"role": "assistant", "content": result["answer"]}])
            print("Follow-up:", result["answer"])
        school = db.resolve_pipe("alero_school_borehole")["pipe"]
        clinic = db.resolve_pipe("alero_clinic_pump")["pipe"]
        assert school["status"] == clinic["status"] == "broken"
        assert results[0]["intent"] == "both" and results[0]["reports"][0]["pipe_id"] == str(school["id"])
        assert results[1]["reports"][0]["pipe_id"] == str(clinic["id"])
        assert results[2]["intent"] == "query" and not results[2]["stored_fact_ids"]
        assert all(r["qdrant_indexed"] for result in results for r in result["reports"])
        with db.connect() as conn:
            rows = conn.execute("SELECT original_text FROM pipe_reports WHERE user_id=%s", ("demo-call-context",)).fetchall()
            assert {row["original_text"] for row in rows} == set(messages[:2])
            assert conn.execute("SELECT count(*) AS n FROM pipe_reports").fetchone()["n"] == before + len(rows)
    finally:
        if kb.client().collection_exists(kb.COLLECTION):
            kb.client().delete_collection(kb.COLLECTION)


@pytest.mark.skipif(os.getenv("RUN_LIVE_LLM") != "1", reason="requires configured Anthropic and Qdrant")
def test_live_proactive_news_demo(registry, monkeypatch):
    import seed_outbound_demo as demo
    from scripts.demo_call import prepare_opening
    monkeypatch.setattr(kb, "COLLECTION", "waterline_news_test_" + uuid4().hex)
    try:
        prepared = demo.seed("isolated-proactive-news")
        monkeypatch.setenv("DEMO_OPENING_PIPE_ID", prepared["opening_pipe_id"])
        opening, _ = prepare_opening()
        print("Opening:", opening)
        assert "school borehole" in opening and "as broken" in opening
        assert "clinic hand pump is reported working" in opening
        context = [{"role": "assistant", "content": opening}]
        messages = ["Where should I go, and what should I bring?",
                    "Is a repair team coming to the Alero school borehole?",
                    "The clinic pump you suggested is broken right now."]
        results = []
        for message in messages:
            result = asyncio.run(g.handle_turn(message, "demo-proactive-news", str(uuid4()), kb.utcnow(), context=context))
            print("Reply:", result["answer"])
            results.append(result)
            context.extend([{"role": "user", "content": message}, {"role": "assistant", "content": result["answer"]}])
        assert [r["intent"] for r in results] == ["query", "query", "report"]
        assert not results[0]["stored_fact_ids"] and not results[1]["stored_fact_ids"]
        assert "side gate" in results[0]["answer"].lower() and "container" in results[0]["answer"].lower()
        assert any(p.get("source_id") == "isolated-proactive-news:school-maintenance" for p in results[1]["sources"])
        clinic = db.resolve_pipe("alero_clinic_pump")["pipe"]
        assert clinic["status"] == "broken"
        assert results[2]["reports"][0]["pipe_id"] == str(clinic["id"])
        assert results[2]["reports"][0]["qdrant_indexed"]
        revised, _ = prepare_opening()
        assert "clinic hand pump is reported working" not in revised
    finally:
        if kb.client().collection_exists(kb.COLLECTION):
            kb.client().delete_collection(kb.COLLECTION)


@pytest.mark.skipif(os.getenv("RUN_LIVE_LLM") != "1", reason="requires configured Anthropic and Qdrant")
def test_live_natural_language_rehearsal(registry, monkeypatch):
    """Optional actual LLM + SQL + Qdrant rehearsal, isolated from the demo data."""
    monkeypatch.setattr(kb, "COLLECTION", "waterline_live_test_" + uuid4().hex)
    kb.initialize()
    async def turn(text, hour):
        return await g.handle_turn(text, "demo-live", str(uuid4()), f"2026-10-17T{hour}:00:00Z")
    try:
        broken = asyncio.run(turn("The Alero School Borehole is broken today.", "08"))
        assert broken["intent"] == "report" and broken["reports"][0]["applied_to_current_status"]
        assert db.resolve_pipe("Alero School Borehole")["pipe"]["status"] == "broken"
        repaired = asyncio.run(turn("The Alero School Borehole was repaired this afternoon and is working again.", "14"))
        assert any(r["applied_to_current_status"] for r in repaired["reports"]), repaired
        assert db.resolve_pipe("Alero School Borehole")["pipe"]["status"] == "operational"
        historical = asyncio.run(turn("The Alero School Borehole was broken last week.", "15"))
        assert not historical["reports"][0]["applied_to_current_status"]
        ambiguous = asyncio.run(turn("The pipe near the school is broken.", "16"))
        assert ambiguous["reports"][0]["resolution_status"] == "ambiguous", ambiguous
        mixed = asyncio.run(turn("The Alero Market Water Point stopped working today. Where else can we go?", "17"))
        assert mixed["intent"] == "both" and mixed["reports"][0]["applied_to_current_status"]
        assert mixed["reports"][0]["qdrant_indexed"]
        assert any(p.get("authoritative_current_status") and p["value"] == "operational" for p in mixed["sources"])
        print("Live mixed answer:", mixed["answer"])
        query = asyncio.run(turn("Which pipes in Alero are currently working?", "18"))
        assert query["intent"] == "query" and not query["stored_fact_ids"]
        print("Live query answer:", query["answer"])
    finally:
        kb.client().delete_collection(kb.COLLECTION)


def test_conservative_name_matching_offline(monkeypatch):
    pipes = [dict(id=uuid4(), name="Alero School Borehole", aliases=["Alero school pipe"], village="Alero"),
             dict(id=uuid4(), name="Kito School Water Point", aliases=["Kito school pipe"], village="Kito")]
    monkeypatch.setattr(db, "get_pipes", lambda village=None: [p for p in pipes if not village or p["village"] == village])
    monkeypatch.setattr(db, "get_pipe_by_id", lambda key: next((p for p in pipes if str(p["id"]) == str(key)), None))
    assert db.resolve_pipe("pipe near the school")["status"] == "ambiguous"
    assert db.resolve_pipe("school", "Alero")["pipe"] == pipes[0]
    assert db.resolve_pipe("Alero school pipe")["pipe"] == pipes[0]
    assert db.resolve_pipe("imaginary spring")["status"] == "unmatched"
    assert db.resolve_pipe(pipe_id=str(uuid4()))["status"] == "unmatched"
    assert db.resolve_pipe(pipe_id=pipes[0]["id"], village="Kito")["status"] == "unmatched"


def test_general_report_and_unclear_without_inventing_asset(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "configured-demo-url")
    monkeypatch.setattr(db, "get_pipes", lambda *args: [])
    model = Mock()
    model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=g.Interpretation(
        intent="report", facts=[g.Fact(statement="The committee accepts maintenance reports on Mondays.")]))
    monkeypatch.setattr(g, "llm", lambda: model)
    monkeypatch.setattr(db, "store_reports", lambda *args: [dict(id=uuid4(), pipe_id=None,
        reported_status=None, applied_to_current_status=False, resolution_status="unmatched", qdrant_indexed=True, candidates=[])])
    result = asyncio.run(g.handle_turn("Synthetic committee notice", "demo-a", "notice", "2026-10-16T12:00:00Z"))
    assert "recorded" in result["answer"] and "Which water point" not in result["answer"]
    model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=g.Interpretation(intent="unclear"))
    unclear = asyncio.run(g.handle_turn("", "demo-a", "empty", "2026-10-16T12:00:00Z"))
    assert unclear["answer"] and "Which water point" in unclear["answer"]
    assert not unclear["stored_fact_ids"]


@pytest.mark.skipif(os.getenv("RUN_BROWSER_SMOKE") != "1", reason="requires Playwright and Chrome")
def test_dashboard_updates_in_browser_without_refresh(registry):
    """A separate SQL write appears through Streamlit's timed fragment, preserving drafts."""
    import socket
    import subprocess
    import sys
    import time
    import httpx
    from playwright.sync_api import sync_playwright, expect
    from psycopg.conninfo import make_conninfo
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "DATABASE_URL": make_conninfo(os.environ["DATABASE_URL"], options=f"-c search_path={registry}")}
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "dashboard.py",
        "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true",
        "--browser.gatherUsageStats", "false", "--server.fileWatcherType", "none"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if httpx.get(url + "/_stcore/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page()
                page.goto(url)
                metrics = page.get_by_test_id("stMetricValue")
                expect(metrics.nth(1)).to_have_text("5", timeout=15000)
                page.get_by_role("tab", name="Ask & report").click()
                page.get_by_role("textbox", name="Message").fill("Draft stays while the map updates")
                page.get_by_role("tab", name="Infrastructure", exact=True).click()
                save(observation(), "browser-live-update")
                # No page.reload(), click, or Streamlit rerun: the timed fragment must update it.
                expect(metrics.nth(1)).to_have_text("4", timeout=10000)
                expect(metrics.nth(2)).to_have_text("4")
                change = page.locator(".waterline-change").first
                expect(change).to_contain_text("Alero school borehole")
                expect(change).to_contain_text("operational")
                expect(change).to_contain_text("broken")
                expect(change).to_contain_text("requires verification")
                event_id = change.get_attribute("data-event-id")
                # The next scheduled tick should settle the animation, not repeat the event.
                expect(change).to_have_class("waterline-change is-stale", timeout=7000)
                assert change.get_attribute("data-event-id") == event_id
                assert page.locator(".waterline-change").count() == 1
                page.emulate_media(reduced_motion="reduce")
                assert change.evaluate("el => getComputedStyle(el).animationName") == "none"

                page.get_by_role("tab", name="Ask & report").click()
                expect(page.get_by_role("textbox", name="Message")).to_have_value("Draft stays while the map updates")
                assert page.get_by_role("link", name="🎙 Open voice demo").count() == 1
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
