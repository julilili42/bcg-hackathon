"""Seed the database. ``python -m reach.ingest.seed --reset`` (offline snapshot) or ``--live``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reach.brain.keywords import KeywordUnderstander
from reach.core.domains import load_domains
from reach.core.service import ReachService
from reach.ingest import demo_overlay, health, wpdx
from reach.settings import get_settings
from reach.storage.db import init_db, make_engine
from reach.storage.repository import Repository


def seed(
    repo: Repository,
    data_dir: Path,
    district: str = "Kisarawe",
    live: bool = False,
    reset: bool = False,
    demo: bool = True,
) -> dict[str, int]:
    if reset:
        repo.clear_all()
    summary: dict[str, int] = {}

    snapshot = data_dir / "wpdx" / f"{district.lower()}.json"
    rows = wpdx.fetch_district(district) if live else wpdx.load_snapshot(snapshot)
    water = wpdx.rows_to_entities(rows)
    for entity, baseline in water:
        repo.upsert_entity(entity)
        if baseline and not repo.reports_for_entity(entity.id, limit=1):
            repo.add_report(baseline)
    summary["water_points"] = len(water)

    health_csv = data_dir / "health" / f"{district.lower()}.csv"
    if health_csv.is_file():
        clinics = health.rows_to_entities(health.load_csv(health_csv))
        for entity, baseline in clinics:
            repo.upsert_entity(entity)
            if baseline and not repo.reports_for_entity(entity.id, limit=1):
                repo.add_report(baseline)
        summary["clinics"] = len(clinics)

    if demo:
        overlay = demo_overlay.load_overlay(data_dir / "demo" / "aliases.csv")
        summary["demo_overlay"] = demo_overlay.apply_overlay(repo, overlay)

    service = ReachService(repo, load_domains(), KeywordUnderstander())
    summary["recomputed"] = service.recompute_all()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--district", default="Kisarawe")
    parser.add_argument("--live", action="store_true", help="fetch from the WPDx API instead of the snapshot")
    parser.add_argument("--reset", action="store_true", help="delete everything first")
    parser.add_argument("--no-demo", action="store_true", help="skip the demo alias overlay")
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    summary = seed(
        Repository(engine), settings.data_dir, args.district, args.live, args.reset, not args.no_demo
    )
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
