from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from reach.core.status import DEFAULT_PARAMS, DISPUTED, UNKNOWN, ReportObs, derive_status, report_weight

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def obs(status: str, channel: str = "sms", days_ago: float = 0) -> ReportObs:
    return ReportObs(status, channel, NOW - timedelta(days=days_ago))


def test_no_reports_is_unknown() -> None:
    d = derive_status([], NOW)
    assert d.status == UNKNOWN and d.confidence == 0.0


def test_fresh_report_wins_over_old_import_baseline() -> None:
    d = derive_status([obs("broken", "import", days_ago=6000), obs("ok", "sms")], NOW)
    assert d.status == "ok"
    assert 0.6 < d.confidence < 0.8


def test_import_baseline_alone_is_unverified_but_shows_status() -> None:
    d = derive_status([obs("broken", "import", days_ago=6000)], NOW)
    assert d.status == "broken"
    assert d.confidence < DEFAULT_PARAMS.verified_min_confidence
    assert not d.verified()


def test_two_conflicting_fresh_reports_are_disputed_and_third_resolves() -> None:
    reports = [obs("broken", "import", 6000), obs("broken", "sms"), obs("ok", "voice")]
    d = derive_status(reports, NOW)
    assert d.status == DISPUTED
    reports.append(obs("broken", "sms"))
    d2 = derive_status(reports, NOW)
    assert d2.status == "broken" and d2.confidence > 0.6


def test_old_live_reports_fall_out_of_window() -> None:
    d = derive_status([obs("ok", "sms", days_ago=120)], NOW)
    assert d.status == UNKNOWN


def test_weight_decays_with_half_life() -> None:
    fresh = report_weight(obs("ok"), NOW)
    week = report_weight(obs("ok", days_ago=7), NOW)
    assert abs(week - fresh / 2) < 1e-9
    assert report_weight(obs("ok", "import", 10_000), NOW) == DEFAULT_PARAMS.import_floor


statuses = st.sampled_from(["ok", "broken", "empty"])
channels = st.sampled_from(["sms", "voice", "web", "import"])


@given(st.lists(st.tuples(statuses, channels, st.floats(0, 400)), max_size=30))
def test_confidence_is_bounded(items: list[tuple[str, str, float]]) -> None:
    d = derive_status([obs(s, c, a) for s, c, a in items], NOW)
    assert 0.0 <= d.confidence <= 1.0
    assert d.total_weight >= 0


@given(
    st.lists(
        st.tuples(statuses, st.sampled_from(["sms", "voice"]), st.floats(0, 60)), min_size=1, max_size=20
    )
)
def test_adding_a_report_for_the_leader_never_flips_the_leader(items: list[tuple[str, str, float]]) -> None:
    reports = [obs(s, c, a) for s, c, a in items]
    d = derive_status(reports, NOW)
    if d.status in (UNKNOWN, DISPUTED):
        return
    d2 = derive_status([*reports, obs(d.status, "sms", 0)], NOW)
    assert d2.status == d.status
