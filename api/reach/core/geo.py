"""Small geo helpers. Straight-line distances; the path factor approximates real walking routes."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0
WALK_SPEED_KMH = 5.0
PATH_FACTOR = 1.3

BBox = tuple[float, float, float, float]  # min_lat, min_lon, max_lat, max_lon


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, h)))


def walk_minutes(distance_km: float) -> int:
    return max(1, round(distance_km * PATH_FACTOR / WALK_SPEED_KMH * 60))


def bbox_around(lat: float, lon: float, radius_km: float) -> BBox:
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.1, math.cos(math.radians(lat))))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


def in_bbox(lat: float, lon: float, bbox: BBox) -> bool:
    min_lat, min_lon, max_lat, max_lon = bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def parse_bbox(raw: str) -> BBox:
    """``minLon,minLat,maxLon,maxLat`` as MapLibre emits it
    -> internal (min_lat, min_lon, max_lat, max_lon)."""
    parts = [float(p) for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox needs four numbers: minLon,minLat,maxLon,maxLat")
    min_lon, min_lat, max_lon, max_lat = parts
    return (min_lat, min_lon, max_lat, max_lon)
