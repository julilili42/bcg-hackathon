from reach.core.geo import bbox_around, haversine_km, in_bbox, parse_bbox, walk_minutes


def test_haversine_known_distance() -> None:
    # Kisarawe town to Dar es Salaam centre is roughly 28 km as the crow flies
    d = haversine_km(-6.905, 39.065, -6.8160, 39.2803)
    assert 24 < d < 28


def test_walk_minutes_scales_with_distance() -> None:
    assert walk_minutes(0) == 1
    assert walk_minutes(1.0) == 16  # 1 km * 1.3 / 5 km/h
    assert walk_minutes(2.0) == 31


def test_bbox_round_trip() -> None:
    box = bbox_around(-6.9, 39.06, 5)
    assert in_bbox(-6.9, 39.06, box)
    assert not in_bbox(-7.5, 39.06, box)
    parsed = parse_bbox("38.5,-7.5,39.1,-6.8")
    assert parsed == (-7.5, 38.5, -6.8, 39.1)
