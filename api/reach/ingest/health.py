"""Health facilities import from the Tanzania Health Facility Registry snapshot (openAFRICA CSV)."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from reach.core.schemas import Entity, Report

IMPORT_REPORTER = "import:hfr"
LEVEL_LABEL = {
    "Dispensary": ("Dispensary", "Zahanati"),
    "Health Center": ("Health Centre", "Kituo cha Afya"),
    "Health Centre": ("Health Centre", "Kituo cha Afya"),
    "Hospital": ("Hospital", "Hospitali"),
    "Clinic": ("Clinic", "Kliniki"),
}


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def rows_to_entities(rows: list[dict[str, str]]) -> list[tuple[Entity, Report | None]]:
    out: list[tuple[Entity, Report | None]] = []
    for row in rows:
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        base = (row.get("name") or row.get("common_name") or "Facility").strip()
        level_raw = (row.get("level") or "").strip()
        en_level, sw_level = LEVEL_LABEL.get(level_raw, (level_raw or "Facility", "Kituo"))
        name = f"{base} {en_level}"
        aliases = {base, f"{sw_level} {base}", f"{base} {sw_level}"}
        common = (row.get("common_name") or "").strip()
        if common and common.lower() != base.lower():
            aliases.add(common)
        facility_id = (row.get("facility_id") or base).strip()
        operating = (row.get("operating_status") or "").strip().lower()
        status = "open" if operating in ("operating", "open", "") else "closed"
        updated = row.get("source_updated") or "2016-06-22"
        try:
            surveyed = datetime.fromisoformat(updated).replace(tzinfo=UTC)
        except ValueError:
            surveyed = datetime(2016, 6, 22, tzinfo=UTC)
        entity = Entity(
            id=f"hfr:{facility_id}",
            domain_id="health",
            name=name,
            aliases=sorted(a for a in aliases if a and a != name),
            lat=lat,
            lon=lon,
            adm1=row.get("region"),
            adm2=row.get("district"),
            adm3=row.get("ward"),
            attributes={
                "level": en_level,
                "ownership": row.get("ownership"),
                "village": row.get("village"),
                "council": row.get("council"),
                "surveyed_on": updated,
            },
            source="hfr",
            external_id=facility_id,
        )
        report = Report(
            entity_id=entity.id,
            reporter_hash=IMPORT_REPORTER,
            channel="import",
            lang=None,
            raw_text=row.get("operating_status"),
            status_claimed=status,
            weight=0.4,
            created_at=surveyed,
        )
        out.append((entity, report))
    return out
