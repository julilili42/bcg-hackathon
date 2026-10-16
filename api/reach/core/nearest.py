"""Nearest working alternative. Verified points (fresh reports) rank before unverified baselines."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from reach.core.geo import haversine_km, walk_minutes
from reach.core.status import DEFAULT_PARAMS, StatusParams


@dataclass(frozen=True)
class GeoCandidate:
    entity_id: str
    name: str
    lat: float
    lon: float
    status: str
    confidence: float


@dataclass(frozen=True)
class Alternative:
    entity_id: str
    name: str
    distance_km: float
    walk_minutes: int
    status: str
    confidence: float
    verified: bool


def nearest_working(
    lat: float,
    lon: float,
    candidates: Iterable[GeoCandidate],
    good_statuses: Iterable[str],
    radius_km: float,
    max_results: int = 3,
    exclude_id: str | None = None,
    params: StatusParams = DEFAULT_PARAMS,
) -> list[Alternative]:
    good = set(good_statuses)
    found: list[Alternative] = []
    for cand in candidates:
        if cand.entity_id == exclude_id or cand.status not in good:
            continue
        dist = haversine_km(lat, lon, cand.lat, cand.lon)
        if dist > radius_km:
            continue
        found.append(
            Alternative(
                entity_id=cand.entity_id,
                name=cand.name,
                distance_km=round(dist, 2),
                walk_minutes=walk_minutes(dist),
                status=cand.status,
                confidence=cand.confidence,
                verified=cand.confidence >= params.verified_min_confidence,
            )
        )
    found.sort(key=lambda a: (not a.verified, a.distance_km, a.entity_id))
    return found[:max_results]
