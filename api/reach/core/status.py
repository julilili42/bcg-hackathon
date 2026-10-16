"""Status derivation (ADR 0006): reports are facts, status is derived.

Every report carries a weight that decays with age. Imported baselines (for example WPDx surveys from
2009) never drop to zero; they keep a small floor so the map can show the last known state as
"unverified" until a fresh report arrives. A baseline is a weak prior (weight 0.3 to 0.4): one fresh
report overrides it, two fresh reports that disagree make the point "disputed". Pure functions, no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

UNKNOWN = "unknown"
DISPUTED = "disputed"
IMPORT = "import"


@dataclass(frozen=True)
class StatusParams:
    half_life_live_days: float = 7.0
    half_life_import_days: float = 365.0
    import_floor: float = 0.15
    window_days: int = 90
    channel_weights: Mapping[str, float] = field(
        default_factory=lambda: {"voice": 1.0, "sms": 1.0, "web": 1.2, IMPORT: 0.4}
    )
    dispute_ratio: float = 0.75
    dispute_min_total: float = 1.5
    unknown_max_total: float = 0.05
    full_confidence_total: float = 1.5
    verified_min_confidence: float = 0.3


DEFAULT_PARAMS = StatusParams()


@dataclass(frozen=True)
class ReportObs:
    status: str
    channel: str
    created_at: datetime
    weight: float | None = None  # stored per report; falls back to the channel weight


@dataclass(frozen=True)
class Derived:
    status: str
    confidence: float
    total_weight: float
    votes: dict[str, float]
    report_count: int

    def verified(self, params: StatusParams = DEFAULT_PARAMS) -> bool:
        return self.status not in (UNKNOWN, DISPUTED) and self.confidence >= params.verified_min_confidence


def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def report_weight(obs: ReportObs, now: datetime, params: StatusParams = DEFAULT_PARAMS) -> float:
    age_days = max(0.0, (as_utc(now) - as_utc(obs.created_at)).total_seconds() / 86400.0)
    base = obs.weight if obs.weight is not None else params.channel_weights.get(obs.channel, 1.0)
    if obs.channel == IMPORT:
        return float(max(params.import_floor, base * 0.5 ** (age_days / params.half_life_import_days)))
    return float(base * 0.5 ** (age_days / params.half_life_live_days))


def derive_status(
    reports: Iterable[ReportObs],
    now: datetime | None = None,
    params: StatusParams = DEFAULT_PARAMS,
) -> Derived:
    now_utc = as_utc(now) if now is not None else datetime.now(UTC)
    cutoff = now_utc - timedelta(days=params.window_days)
    votes: dict[str, float] = {}
    live_votes: dict[str, float] = {}
    count = 0
    for obs in reports:
        if obs.channel != IMPORT and as_utc(obs.created_at) < cutoff:
            continue
        weight = report_weight(obs, now_utc, params)
        votes[obs.status] = votes.get(obs.status, 0.0) + weight
        if obs.channel != IMPORT:
            live_votes[obs.status] = live_votes.get(obs.status, 0.0) + weight
        count += 1
    total = sum(votes.values())
    if not votes or total <= params.unknown_max_total:
        return Derived(UNKNOWN, 0.0, round(total, 4), votes, count)
    # A dispute is between people, so it is judged on live reports only; priors never create one.
    live_total = sum(live_votes.values())
    if live_total >= params.dispute_min_total and len(live_votes) > 1:
        live_ranked = sorted(live_votes.values(), reverse=True)
        if live_ranked[1] >= params.dispute_ratio * live_ranked[0]:
            confidence = round(max(0.0, 1.0 - live_ranked[1] / live_ranked[0]), 3)
            return Derived(DISPUTED, confidence, round(total, 4), votes, count)
    ranked = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))
    leader, lead_w = ranked[0]
    confidence = (lead_w / total) * min(1.0, total / params.full_confidence_total)
    return Derived(leader, round(confidence, 3), round(total, 4), votes, count)
