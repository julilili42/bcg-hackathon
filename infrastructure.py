"""PostgreSQL registry and append-only community observations; no model-generated SQL."""
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()
DEFAULT_URL = "postgresql://waterline:waterline@localhost:5433/waterline_live"
STATUSES = ("operational", "broken", "low_flow", "under_repair", "unsafe", "unknown")


def enabled():
    return bool(os.getenv("DATABASE_URL", DEFAULT_URL).strip())


def connect():
    return psycopg.connect(os.getenv("DATABASE_URL", DEFAULT_URL), row_factory=dict_row, connect_timeout=5)


def initialize():
    with connect() as conn:
        conn.execute(Path(__file__).with_name("schema.sql").read_text())


def get_pipes(village=None, status=None):
    with connect() as conn:
        return conn.execute("SELECT pipes.*, (SELECT count(*) FROM pipe_reports WHERE pipe_id=pipes.id) AS report_count "
                            "FROM pipes WHERE (%s::text IS NULL OR lower(village)=lower(%s)) "
                            "AND (%s::text IS NULL OR status=%s) ORDER BY village,name",
                            (village, village, status, status)).fetchall()


def get_pipe_by_id(pipe_id):
    try:
        pipe_id = UUID(str(pipe_id))
    except (ValueError, TypeError):
        return None
    with connect() as conn:
        return conn.execute("SELECT * FROM pipes WHERE id=%s", (pipe_id,)).fetchone()


def normalize(text):
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower().replace("_", " ")))


def resolve_pipe(name=None, village=None, location=None, pipe_id=None):
    """Return a match only when unique. IDs are checked against the registry."""
    if pipe_id:
        pipe = get_pipe_by_id(pipe_id)
        if pipe and (not village or normalize(pipe["village"]) == normalize(village)):
            return {"status": "matched", "pipe": pipe, "candidates": []}
    pipes = get_pipes(village)
    needle = normalize(name or location)
    if not needle:
        return {"status": "unmatched", "pipe": None, "candidates": []}
    exact = [p for p in pipes if needle in {normalize(p["name"]), *(normalize(a) for a in p["aliases"])}]
    candidates = exact
    if not candidates:
        # Discard generic infrastructure words so 'near the school' cannot select a village.
        generic = set("the a an by near next to at in of water point pipe pump borehole tap hand is".split())
        words = set(needle.split()) - generic
        candidates = [p for p in pipes if words and any(
            words <= (set(normalize(n).split()) - generic) for n in [p["name"], *p["aliases"]])]
        if not candidates and words:
            scored = [(max(SequenceMatcher(None, needle, normalize(n)).ratio()
                           for n in [p["name"], *p["aliases"]]), p) for p in pipes]
            scored.sort(key=lambda pair: pair[0], reverse=True)
            if scored and scored[0][0] >= .84:
                candidates = [p for score, p in scored if score >= scored[0][0] - .08]
    return {"status": "matched" if len(candidates) == 1 else "ambiguous" if candidates else "unmatched",
            "pipe": candidates[0] if len(candidates) == 1 else None, "candidates": candidates}


def timestamp(value):
    if not value:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Observation timestamps must include a timezone")
    return dt.astimezone(timezone.utc)


def report_uuid(turn_id, index):
    return uuid5(NAMESPACE_URL, f"waterline:report:{turn_id}:{index}")


def save_pipe_report(fact, message, user_id, turn_id, index, received_at):
    resolution = resolve_pipe(fact.asset_name or fact.asset_id, fact.village, pipe_id=fact.asset_id)
    pipe = resolution["pipe"]
    received = timestamp(received_at)
    observed = timestamp(fact.observed_at)
    if observed is None and fact.time_basis == "present":
        observed = received
    # Future and ambiguous observations are retained without applying them.
    status = {"working": "operational", "repaired": "operational", "not_working": "broken"}.get(fact.value, fact.value)
    status = status if fact.attribute == "operational_status" and status in STATUSES else None
    report_id = report_uuid(turn_id, index)
    with connect() as conn:
        if pipe:
            pipe = conn.execute("SELECT * FROM pipes WHERE id=%s FOR UPDATE", (pipe["id"],)).fetchone()
        inserted = conn.execute("""INSERT INTO pipe_reports
            (id,pipe_id,user_id,original_text,statement,reported_status,observed_at,reported_at,
             resolution_status,turn_id,fact_index,asset_name,village)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING RETURNING *""",
            (report_id, pipe["id"] if pipe else None, user_id, message, fact.statement, status,
             observed, received, resolution["status"], turn_id, index,
             pipe["name"] if pipe else fact.asset_name, pipe["village"] if pipe else fact.village)).fetchone()
        if inserted:
            current_time = pipe["status_observed_at"] if pipe else None
            apply = bool(pipe and status and observed and observed <= received and
                         (current_time is None or observed >= current_time))
            conflict = bool(pipe and status and observed and current_time and
                            status != pipe["status"] and abs(observed - current_time) <= timedelta(days=1))
            if apply:
                conn.execute("""UPDATE pipes SET status=%s,status_observed_at=%s,status_updated_at=now(),
                    latest_report_id=%s,needs_verification=true WHERE id=%s""",
                    (status, observed, report_id, pipe["id"]))
                conn.execute("UPDATE pipe_reports SET applied_to_current_status=true WHERE id=%s", (report_id,))
            if pipe and conflict:
                conn.execute("UPDATE pipes SET needs_verification=true WHERE id=%s", (pipe["id"],))
        report = conn.execute("SELECT * FROM pipe_reports WHERE id=%s", (report_id,)).fetchone()
    return {**report, "candidates": [p["name"] for p in resolution["candidates"]]}


def get_pipe_history(pipe_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM pipe_reports WHERE pipe_id=%s ORDER BY observed_at DESC NULLS LAST,reported_at DESC LIMIT 100",
                            (pipe_id,)).fetchall()


def mark_indexed(report_id):
    with connect() as conn:
        conn.execute("UPDATE pipe_reports SET qdrant_indexed=true WHERE id=%s", (report_id,))


def index_report(report):
    import knowledge as kb
    payload = dict(text=report["statement"], source_text=report["original_text"],
                   record_type="community_report", source_id=report["turn_id"], chunk_index=report["fact_index"],
                   report_id=str(report["id"]), pipe_id=str(report["pipe_id"]) if report["pipe_id"] else None,
                   asset_id=str(report["pipe_id"]) if report["pipe_id"] else None,
                   asset_name=report["asset_name"], village=report["village"],
                   user_id=report["user_id"], source_type="community_user", verification_status="unverified",
                   observed_at=report["observed_at"].isoformat() if report["observed_at"] else None,
                   reported_at=report["reported_at"].isoformat(), reported_status=report["reported_status"],
                   attribute="operational_status" if report["reported_status"] else None,
                   value=report["reported_status"], synthetic=True)
    kb.ingest(payload, point_id=str(report["id"]))
    mark_indexed(report["id"])


def store_reports(facts, message, user_id, turn_id, received_at):
    reports = []
    for index, fact in enumerate(facts):
        report = save_pipe_report(fact, message, user_id, turn_id, index, received_at)
        if not report["qdrant_indexed"]:
            try:
                index_report(report)
                report["qdrant_indexed"] = True
            except Exception:
                logging.exception("Qdrant indexing failed for committed report %s; run reindex.py", report["id"])
        reports.append(report)
    return reports


def reindex():
    with connect() as conn:
        pending = conn.execute("SELECT * FROM pipe_reports WHERE NOT qdrant_indexed ORDER BY reported_at").fetchall()
    failed = 0
    for report in pending:
        try:
            index_report(report)
        except Exception:
            logging.exception("Reindex failed for report %s", report["id"])
            failed += 1
    return len(pending) - failed, failed


if __name__ == "__main__":
    initialize()
    print("Infrastructure schema initialized.")
