"""All places, assets, notices and observations below are FICTIONAL demo fixtures."""
from knowledge import initialize, ingest
import infrastructure as db

ASSETS = [
    ("alero_clinic_pump", "Alero", "Alero clinic hand pump"),
    ("alero_school_borehole", "Alero", "Alero school borehole"),
    ("alero_market_tap", "Alero", "Alero market tap"),
    ("lumwa_school_borehole", "Lumwa", "Lumwa school borehole"),
    ("lumwa_clinic_pump", "Lumwa", "Lumwa clinic hand pump"),
    ("palaro_market_tap", "Palaro", "Palaro market tap"),
]


def seed():
    initialize()
    if db.enabled():
        from seed_infrastructure import seed as seed_registry
        seed_registry()
    ids = []
    for asset, village, name in ASSETS:
        pipe = db.resolve_pipe(asset)["pipe"] if db.enabled() else None
        common = dict(asset_id=str(pipe["id"]) if pipe else asset, village=village, asset_name=name,
            record_type="document_chunk", user_id=None, synthetic=True,
            source_type="community_document", verification_status="unverified", chunk_index=0)
        if not db.enabled():
            ids.append(ingest({**common, "source_id": f"demo-registry-{asset}",
                "text": f"SYNTHETIC DEMO REGISTRY: {name} is a fictional water point in fictional {village}. No coordinates or water-quality evidence are available.",
                "document_date": "2023-01-01T00:00:00Z"}))
        for index, day in enumerate(("2026-10-10", "2026-10-15")):
            if asset == "alero_market_tap":
                day = "2023-01-02"
            ids.append(ingest({**common, "source_id": f"demo-status-{asset}-{index}",
                "text": f"SYNTHETIC DEMO community observation: {name} was reported working on {day}. This is not a water-safety assessment.",
                "attribute": "operational_status", "value": "working",
                "observed_at": f"{day}T07:00:00Z", "reported_at": f"{day}T08:00:00Z"}))
    notices = [
        ("maintenance", "For this fictional demo, report maintenance problems to the village water committee. A scheduled repair visit does not establish a successful repair."),
        ("safety", "Operational status does not establish that water is safe to drink. This demo contains no verified water-quality tests."),
        ("visit", "A fictional repair visit to Alero clinic pump was scheduled for 2026-10-16. The schedule does not confirm repair or current operation."),
    ]
    for key, text in notices:
        ids.append(ingest(dict(text="SYNTHETIC DEMO NOTICE: " + text, source_text=text,
            source_id=f"demo-notice-{key}", chunk_index=0, record_type="document_chunk",
            source_type="community_document", verification_status="unverified", synthetic=True,
            user_id=None, document_date="2026-10-15T09:00:00Z",
            village="Alero" if key == "visit" else None)))
    return ids


if __name__ == "__main__":
    print(f"Seeded {len(seed())} synthetic evidence records (safe to rerun).")
