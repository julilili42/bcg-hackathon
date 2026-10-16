"""Water Point Data Exchange import (ADR 0003). Snapshot file by default, live Socrata API on request."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from reach.core.schemas import Entity, Report

WPDX_URL = "https://data.waterpointdata.org/resource/eqje-vguj.json"
SELECT_FIELDS = (
    "wpdx_id,row_id,lat_deg,lon_deg,status_id,status_clean,status,water_source_clean,"
    "water_source_category,water_tech_clean,clean_adm1,clean_adm2,clean_adm3,report_date,"
    "install_year,installer,served_population,local_population,rehab_priority,crucialness,"
    "pressure,staleness_score,days_since_report,subjective_quality_clean,pay_clean,management,source,notes"
)
SOURCE_SHORT = {
    "Borehole/Tubewell": "Borehole",
    "Protected Spring": "Spring",
    "Unprotected Spring": "Spring",
    "Protected Well": "Well",
    "Unprotected Well": "Well",
    "Rainwater Harvesting": "Rainwater",
    "Piped Water": "Tap",
    "Surface Water": "Surface",
}
IMPORT_REPORTER = "import:wpdx"


def load_snapshot(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("snapshot must be a JSON array")
    return [row for row in data if isinstance(row, dict)]


def fetch_district(
    district: str, country: str = "Tanzania", client: httpx.Client | None = None, page: int = 1000
) -> list[dict[str, Any]]:
    own = client is None
    http = client or httpx.Client(timeout=60.0)
    rows: list[dict[str, Any]] = []
    offset = 0
    try:
        while True:
            params = {
                "$select": SELECT_FIELDS,
                "$where": f"clean_country_name='{country}' AND clean_adm2='{district}' AND is_latest=true",
                "$order": "row_id",
                "$limit": str(page),
                "$offset": str(offset),
            }
            resp = http.get(WPDX_URL, params=params)
            resp.raise_for_status()
            batch = resp.json()
            rows.extend(batch)
            if len(batch) < page:
                break
            offset += page
    finally:
        if own:
            http.close()
    return rows


def map_status(row: dict[str, Any]) -> str | None:
    clean = (row.get("status_clean") or "").strip()
    if clean.startswith("Functional"):
        return "ok"
    if clean.startswith("Non-Functional, dry"):
        return "empty"
    if clean.startswith("Non-Functional") or clean.startswith("Abandoned"):
        return "broken"
    sid = (row.get("status_id") or "").strip().lower()
    if sid == "yes":
        return "ok"
    if sid == "no":
        return "broken"
    return None


def _parse_date(raw: str | None) -> datetime:
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "")).replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime(2009, 1, 1, tzinfo=UTC)


def _int(raw: Any) -> int | None:
    try:
        return int(float(raw)) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


def generate_names(rows: list[dict[str, Any]]) -> list[str]:
    """``<ward> <source type> <n>``; the ordinal is dropped when a ward has one point of that type."""
    keys = []
    for row in rows:
        ward = (row.get("clean_adm3") or row.get("clean_adm2") or "Unknown").strip()
        short = SOURCE_SHORT.get((row.get("water_source_clean") or "").strip(), "Water point")
        keys.append((ward, short))
    totals = Counter(keys)
    seen: Counter[tuple[str, str]] = Counter()
    names = []
    for key in keys:
        seen[key] += 1
        ward, short = key
        names.append(f"{ward} {short}" if totals[key] == 1 else f"{ward} {short} {seen[key]}")
    return names


def rows_to_entities(rows: list[dict[str, Any]]) -> list[tuple[Entity, Report | None]]:
    ordered = sorted(rows, key=lambda r: int(r.get("row_id") or 0))
    names = generate_names(ordered)
    out: list[tuple[Entity, Report | None]] = []
    for row, name in zip(ordered, names, strict=True):
        try:
            lat, lon = float(row["lat_deg"]), float(row["lon_deg"])
        except (KeyError, TypeError, ValueError):
            continue
        row_id = str(row.get("row_id") or row.get("wpdx_id"))
        entity_id = f"wpdx:{row_id}"
        attributes: dict[str, str | int | float | bool | None] = {
            "water_source": row.get("water_source_clean"),
            "water_tech": row.get("water_tech_clean"),
            "installer": row.get("installer"),
            "install_year": _int(row.get("install_year")),
            "payment": row.get("pay_clean"),
            "quality": row.get("subjective_quality_clean"),
            "management": row.get("management"),
            "wpdx_status_raw": row.get("status_clean"),
            "survey_source": row.get("source"),
            "surveyed_on": (row.get("report_date") or "")[:10] or None,
        }
        entity = Entity(
            id=entity_id,
            domain_id="water",
            name=name,
            aliases=[],
            lat=lat,
            lon=lon,
            adm1=row.get("clean_adm1"),
            adm2=row.get("clean_adm2"),
            adm3=row.get("clean_adm3"),
            attributes={k: v for k, v in attributes.items() if v not in (None, "")},
            source="wpdx",
            external_id=row.get("wpdx_id"),
            served_population=_int(row.get("served_population")),
        )
        status = map_status(row)
        report = (
            Report(
                entity_id=entity_id,
                reporter_hash=IMPORT_REPORTER,
                channel="import",
                lang=None,
                raw_text=row.get("status"),
                status_claimed=status,
                weight=0.4,
                created_at=_parse_date(row.get("report_date")),
            )
            if status
            else None
        )
        out.append((entity, report))
    return out
