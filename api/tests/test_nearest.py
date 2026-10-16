from reach.core.nearest import GeoCandidate, nearest_working

ORIGIN = (-6.9000, 39.0600)
CANDS = [
    GeoCandidate("near-unverified", "Near baseline", -6.9010, 39.0610, "ok", 0.1),
    GeoCandidate("far-verified", "Far verified", -6.9200, 39.0800, "ok", 0.8),
    GeoCandidate("broken", "Broken", -6.9005, 39.0605, "broken", 0.9),
    GeoCandidate("self", "Self", *ORIGIN, "ok", 0.9),
    GeoCandidate("too-far", "Too far", -7.5, 39.5, "ok", 0.9),
]


def test_verified_ranks_before_unverified_and_excludes_self() -> None:
    alts = nearest_working(*ORIGIN, CANDS, ["ok"], radius_km=15, exclude_id="self")
    assert [a.entity_id for a in alts] == ["far-verified", "near-unverified"]
    assert alts[0].verified and not alts[1].verified
    assert alts[0].walk_minutes > alts[1].walk_minutes


def test_radius_and_max_results() -> None:
    alts = nearest_working(*ORIGIN, CANDS, ["ok"], radius_km=0.5, max_results=1)
    assert [a.entity_id for a in alts] == ["self"]
