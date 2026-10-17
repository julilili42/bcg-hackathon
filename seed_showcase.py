"""Seed an append-only, three-turn fictional showcase in the configured SQL/Qdrant stores."""
import argparse
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import infrastructure as db
import knowledge as kb
from seed_infrastructure import seed as seed_registry

DEFAULT_RUN_ID = "hackathon-showcase-v1"
PROMPTS = [
    "The Alero clinic hand pump is broken right now. Which other water point in Alero is reported working?",
    "Is the Alero clinic hand pump working? Does the repair notice confirm it was fixed?",
    "I just used the Alero clinic hand pump and it is working again now. Which water points in Alero are reported working?",
]
BASELINE = [
    ("alero_clinic_pump", "operational"),
    ("alero_school_borehole", "operational"),
    ("alero_market_tap", "low_flow"),
    ("alero_riverside_point", "under_repair"),
]


def seed(run_id=DEFAULT_RUN_ID, baseline=None):
    baseline = BASELINE if baseline is None else baseline
    seed_registry()
    kb.initialize()
    # Preserve the first run's clock on retries. A new run ID explicitly prepares a fresh baseline.
    first_id = db.report_uuid(f"{run_id}:baseline:alero_clinic_pump", 0)
    with db.connect() as conn:
        existing = conn.execute("SELECT reported_at FROM pipe_reports WHERE id=%s", (first_id,)).fetchone()
    anchor = existing["reported_at"] if existing else datetime.now(timezone.utc)
    assets = {key: db.resolve_pipe(key)["pipe"] for key, _ in BASELINE}
    if not all(assets.values()):
        raise RuntimeError("Showcase assets could not be uniquely resolved.")
    reports = []

    def report(key, value, observed, label):
        pipe = assets[key]
        statement = (f"SYNTHETIC DEMO observation: {pipe['name']} was reported {value.replace('_', ' ')} "
                     f"at {observed.isoformat()}. This is unverified and is not a water-quality assessment.")
        fact = SimpleNamespace(statement=statement, asset_name=pipe["name"], asset_id=str(pipe["id"]),
            village="Alero", attribute="operational_status", value=value,
            observed_at=observed.isoformat(), time_basis="explicit")
        saved = db.store_reports([fact], statement, "demo-showcase-seed", f"{run_id}:{label}:{key}", anchor.isoformat())[0]
        if not saved["qdrant_indexed"]:
            raise RuntimeError("A showcase observation was saved but indexing is pending; run reindex.py.")
        reports.append(saved)

    # Upload old events now, then apply a genuinely newer baseline. Never remove historical evidence.
    report("alero_clinic_pump", "broken", anchor - timedelta(days=3), "history-failure")
    report("alero_clinic_pump", "operational", anchor - timedelta(days=2), "history-repair")
    for key, value in baseline:
        report(key, value, anchor, "baseline")

    scheduled = (anchor + timedelta(hours=1)).isoformat()
    notices = [
        ("school-access", "alero_school_borehole",
         "The Alero school borehole is available for community water collection in this fictional demo. "
         "Residents should queue at the school gate. Check the latest community status report before relying on it. "
         "This notice does not certify water quality."),
        ("clinic-repair-plan", "alero_clinic_pump",
         f"A routine maintenance visit to the Alero clinic hand pump is scheduled for {scheduled}. "
         "This is a plan, not a completed repair or an inspection. There is no repair-completion confirmation in this notice. "
         "New community observations may report a failure before the planned visit."),
        ("market-low-flow", "alero_market_tap",
         "The Alero market tap has a reduced-flow community report in this fictional demo. "
         "Do not describe it as fully operational; consult current registry reports before suggesting it as an alternative."),
        ("riverside-repair", "alero_riverside_point",
         "The Alero Riverside Water Point is undergoing maintenance in this fictional demo. "
         "A planned repair does not establish successful operation. There is no completion notice."),
        ("maintenance-contact", None,
         "In fictional Alero, maintenance faults can be reported to the village water committee at the community hall. "
         "Residents should include the water point name and the time observed. The committee notice does not verify individual reports."),
        ("water-safety", None,
         "Operational means equipment is reported to deliver water; it does not mean the water is safe to drink. "
         "This fictional showcase has no verified drinking-water test results. Community reports and repairs do not establish potability."),
    ]
    document_ids = []
    for label, key, text in notices:
        pipe = assets.get(key)
        text = "SYNTHETIC DEMO NOTICE: " + text
        document_ids.append(kb.ingest(dict(text=text, source_text=text,
            source_id=f"{run_id}:{label}", chunk_index=0, record_type="document_chunk",
            source_type="community_document", verification_status="unverified", user_id=None,
            village="Alero", asset_id=str(pipe["id"]) if pipe else None,
            asset_name=pipe["name"] if pipe else None, document_date=anchor.isoformat(), synthetic=True)))
    return dict(run_id=run_id, prepared_at=anchor.isoformat(), report_ids=[str(r["id"]) for r in reports],
                document_ids=document_ids, prompts=PROMPTS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID,
        help="Same ID retries idempotently; a new ID appends fresh baseline reports for another rehearsal.")
    result = seed(parser.parse_args().run_id)
    print(f"Prepared {result['run_id']}: 6 synthetic observations + 6 notices in {kb.COLLECTION}.")
    for key, expected in BASELINE:
        pipe = db.resolve_pipe(key)["pipe"]
        print(f"{pipe['name']}: {pipe['status']} (baseline: {expected})")
    print("Run these in order; use a second resident or a new call for turn 2:")
    for index, prompt in enumerate(PROMPTS, 1):
        print(f"{index}. {prompt}")
