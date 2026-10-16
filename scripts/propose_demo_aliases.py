#!/usr/bin/env python3
"""Write data/demo/aliases.csv: memorable Swahili aliases on real points near the demo centre.

Usage: PYTHONPATH=api uv run python scripts/propose_demo_aliases.py [lat lon]
The first point becomes "Shule"; the others are named in order of distance from it so the nearest
verified working alternative to Shule is always "Kanisa".
"""

from __future__ import annotations

import csv
import sys

from reach.core.geo import haversine_km
from reach.ingest import health, wpdx
from reach.settings import REPO_ROOT

WATER_ALIASES = [
    ("Shule", "ok"),
    ("Kanisa", "ok"),
    ("Soko", "broken"),
    ("Msikiti", "ok"),
    ("Bwawa", "empty"),
    ("Stesheni", "ok"),
]
CLINIC_BASELINES = {
    "105431-1": "open",
    "104356-1": "open",
    "104371-0": "open",
}  # Msanga, Marui Mipera, Masaki


def main() -> int:
    lat = float(sys.argv[1]) if len(sys.argv) > 2 else -6.905
    lon = float(sys.argv[2]) if len(sys.argv) > 2 else 39.065
    data = REPO_ROOT / "data"
    water = [e for e, _ in wpdx.rows_to_entities(wpdx.load_snapshot(data / "wpdx" / "kisarawe.json"))]
    water.sort(key=lambda e: haversine_km(lat, lon, e.lat, e.lon))
    anchor = water[0]
    rest = sorted(water[1:], key=lambda e: haversine_km(anchor.lat, anchor.lon, e.lat, e.lon))
    chosen = [anchor, *rest[: len(WATER_ALIASES) - 1]]
    rows = []
    for entity, (alias, status) in zip(chosen, WATER_ALIASES, strict=True):
        km = haversine_km(anchor.lat, anchor.lon, entity.lat, entity.lon)
        rows.append(
            {
                "entity_id": entity.id,
                "alias": alias,
                "baseline_status": status,
                "note": f"{entity.name}; {km:.1f} km from Shule",
            }
        )
    clinics = {
        e.external_id: e
        for e, _ in health.rows_to_entities(health.load_csv(data / "health" / "kisarawe.csv"))
    }
    for fid, status in CLINIC_BASELINES.items():
        if fid in clinics:
            rows.append(
                {
                    "entity_id": clinics[fid].id,
                    "alias": "",
                    "baseline_status": status,
                    "note": clinics[fid].name,
                }
            )
    out = data / "demo" / "aliases.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["entity_id", "alias", "baseline_status", "note"])
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['entity_id']:14s} {row['alias']:9s} {row['baseline_status']:7s} {row['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
