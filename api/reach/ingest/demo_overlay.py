"""Demo overlay: memorable aliases and a known starting state for a handful of real entities.

``data/demo/aliases.csv`` columns: entity_id, alias, baseline_status (optional). The alias becomes the
display name (what callers say and what the map shows); the generated name is kept as an alias so
speech like "Kisarawe Rainwater 3" still matches. A baseline status is
recorded as a fresh, weak import report (weight 0.25) so the point starts the demo in a known state
that the first live report overrides.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from reach.core.schemas import Report
from reach.storage.repository import Repository

DEMO_REPORTER = "demo:overlay"


def load_overlay(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def apply_overlay(repo: Repository, rows: list[dict[str, str]], now: datetime | None = None) -> int:
    stamp = now or datetime.now(UTC)
    applied = 0
    for row in rows:
        entity_id = (row.get("entity_id") or "").strip()
        alias = (row.get("alias") or "").strip()
        entity = repo.get_entity(entity_id) if entity_id else None
        if entity is None:
            continue
        if alias and alias != entity.name:
            others = [a for a in entity.aliases if a != alias]
            repo.upsert_entity(entity.model_copy(update={"name": alias, "aliases": [*others, entity.name]}))
        status = (row.get("baseline_status") or "").strip()
        if status:
            repo.add_report(
                Report(
                    entity_id=entity_id,
                    reporter_hash=DEMO_REPORTER,
                    channel="import",
                    lang=None,
                    raw_text=None,
                    status_claimed=status,
                    note="demo baseline",
                    weight=0.25,
                    created_at=stamp,
                )
            )
        applied += 1
    return applied
