"""Prepare fictional proactive-call evidence; never place a call or store scripted answers."""
import argparse

import infrastructure as db
import knowledge as kb
from seed_showcase import seed as seed_showcase

BASELINE = [
    ("alero_clinic_pump", "operational"),
    ("alero_school_borehole", "broken"),
    ("alero_market_tap", "low_flow"),
    ("alero_riverside_point", "under_repair"),
]


def seed(run_id="outbound-news-v1"):
    result = seed_showcase(run_id, baseline=BASELINE)
    school = db.resolve_pipe("alero_school_borehole")["pipe"]
    clinic = db.resolve_pipe("alero_clinic_pump")["pipe"]
    notices = [
        ("school-maintenance", school,
         "The fictional Alero village water committee plans an inspection of the Alero school borehole "
         "after a community fault report. A visit has been requested, but its arrival time is not confirmed. "
         "There is no completed-repair confirmation or promised restoration time in this notice. "
         "Residents can ask the committee at the community hall about maintenance. "
         "Check the latest dated operational reports for the present reported condition."),
        ("clinic-collection-access", clinic,
         "Community water collection at the fictional Alero clinic hand pump uses the clinic's side gate. "
         "A caretaker can show residents the collection queue. Bring your own clean water container. "
         "The community collection arrangement has no collection fee. Ask the caretaker for help if carrying "
         "a container is difficult. This is access information, not a guarantee that the pump is working now; "
         "check the latest dated operational report. No walking route, distance or travel time is available."),
        ("clinic-water-quality", clinic,
         "No verified drinking-water test result is available for the fictional Alero clinic hand pump "
         "in this demo. A report that the equipment delivers water does not establish that the water is "
         "safe to drink. The collection-access notice and a clean container do not certify water quality."),
    ]
    for label, pipe, text in notices:
        text = "SYNTHETIC DEMO COMMUNITY NOTICE: " + text
        result["document_ids"].append(kb.ingest(dict(text=text, source_text=text,
            record_type="document_chunk", source_id=f"{run_id}:{label}", chunk_index=0,
            source_type="community_document", verification_status="unverified", user_id=None,
            village=pipe["village"], asset_id=str(pipe["id"]), asset_name=pipe["name"],
            document_date=result["prepared_at"], synthetic=True)))
    result["opening_pipe_id"] = str(school["id"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="outbound-news-v1",
        help="Use a new ID to append a fresh starting state for another rehearsal.")
    result = seed(parser.parse_args().run_id)
    print(f"Prepared {len(result['report_ids'])} synthetic observations and {len(result['document_ids'])} notices in {kb.COLLECTION}.")
    print("DEMO_OPENING_PIPE_ID=" + result["opening_pipe_id"])
    for key, expected in BASELINE:
        pipe = db.resolve_pipe(key)["pipe"]
        print(f"{pipe['name']}: {pipe['status']} (starting state: {expected})")
