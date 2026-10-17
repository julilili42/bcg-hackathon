"""Idempotent fictional registry. Rerunning never resets a resident's newer status."""
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import infrastructure as db
from seed import ASSETS

DEMO_ASSETS = [*ASSETS,
    ("alero_riverside_point", "Alero", "Alero Riverside Water Point"),
    ("kito_community_tap", "Kito", "Kito Community Tap"),
    ("kito_health_borehole", "Kito", "Kito Health Centre Borehole"),
    ("kito_school_point", "Kito", "Kito School Water Point"),
    ("lumwa_east_tap", "Lumwa", "Lumwa East Tap"),
    ("palaro_clinic_pump", "Palaro", "Palaro Clinic Pump"),
]


def seed():
    db.initialize()
    states = ["operational", "operational", "operational", "broken", "low_flow", "under_repair",
              "unknown", "operational", "unsafe", "operational", "low_flow", "broken"]
    for index, (key, village, name) in enumerate(DEMO_ASSETS):
        pipe_id = uuid5(NAMESPACE_URL, "waterline:pipe:" + key)
        aliases = [key, name.lower(), name.replace("borehole", "pipe").replace("Borehole", "pipe")]
        if key == "alero_market_tap":
            aliases.append("Alero Market Water Point")
        if "school" in key:
            aliases.extend([f"{village} School pipe", f"{village} School water point"])
        with db.connect() as conn:
            conn.execute("""INSERT INTO pipes(id,name,aliases,village,description,latitude,longitude)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                (pipe_id, name, aliases, village,
                 "FICTIONAL DEMO asset. Coordinates are illustrative and do not identify real infrastructure.",
                 2.70 + index // 3 * .035 + index % 3 * .003, 32.00 + index // 3 * .04 + index % 3 * .004))
        fact = SimpleNamespace(asset_name=name, asset_id=str(pipe_id), village=village,
            observed_at="2026-10-15T07:00:00Z", time_basis="explicit",
            attribute="operational_status", value=states[index],
            statement=f"SYNTHETIC DEMO: {name} reported {states[index]} on 2026-10-15; unverified.")
        db.save_pipe_report(fact, fact.statement, "demo-seed", f"seed-infrastructure-{key}", 0,
                            "2026-10-15T08:00:00Z")
    return len(DEMO_ASSETS)


if __name__ == "__main__":
    print(f"Seeded {seed()} FICTIONAL infrastructure assets. Existing reports preserved.")
