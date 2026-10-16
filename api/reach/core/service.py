"""The one loop every channel calls: understand -> resolve entity -> record -> derive status -> reply.

Follow-up questions (ADR 0010) are asked only when a slot is missing: a status without a place, two
equally good places, or one uncertain place with a status. The open question is stored per sender and
channel for a few minutes; the next message answers it or simply replaces it.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol

from reach.core.domains import DomainConfig, detect_domain
from reach.core.matching import NameCandidate, best_matches, normalize
from reach.core.nearest import GeoCandidate, nearest_working
from reach.core.schemas import (
    AlternativeOut,
    Channel,
    Entity,
    InboundMessage,
    Lang,
    OutboundReply,
    PendingKind,
    PendingQuestion,
    Report,
    Understanding,
)
from reach.core.status import (
    DEFAULT_PARAMS,
    DISPUTED,
    UNKNOWN,
    Derived,
    ReportObs,
    StatusParams,
    derive_status,
)
from reach.storage.repository import Repository


class Understander(Protocol):
    name: str

    def understand(
        self,
        text: str,
        domain: DomainConfig,
        candidates: list[NameCandidate],
        lang_hint: Lang | None,
    ) -> Understanding: ...


def hash_reporter(raw: str, salt: str) -> str:
    """Salted SHA-256 of the sender identity (ADR 0004). The raw value is never stored."""
    return hashlib.sha256(f"{salt}:{raw.strip()}".encode()).hexdigest()


def conversation_key(channel: str, reporter_hash: str) -> str:
    return f"{channel}:{reporter_hash}"


class RateLimiter:
    """Sliding window per key, in memory. Enough for one instance; swap for storage when scaling."""

    def __init__(self, max_events: int, window_s: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_events = max_events
        self.window_s = window_s
        self._clock = clock
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        q = self._events.setdefault(key, deque())
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= self.max_events:
            return False
        q.append(now)
        return True


AMBIGUITY_MARGIN = 0.05
PENDING_TTL = timedelta(minutes=10)
MAX_FOLLOW_UPS = 2
YES_WORDS = frozenset({"yes", "y", "yeah", "yep", "ok", "okay", "ndiyo", "ndio", "sawa", "eeh", "1"})
NO_WORDS = frozenset({"no", "n", "nope", "hapana", "siyo", "sio", "la", "2"})


class ReachService:
    def __init__(
        self,
        repo: Repository,
        domains: Mapping[str, DomainConfig],
        understander: Understander,
        default_domain: str = "water",
        confirm_thresholds: Mapping[str, float] | None = None,
        params: StatusParams = DEFAULT_PARAMS,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.repo = repo
        self.domains = domains
        self.understander = understander
        self.default_domain = default_domain if default_domain in domains else next(iter(domains))
        self.confirm_thresholds = dict(confirm_thresholds or {"voice": 0.6, "sms": 0.4, "web": 0.0})
        self.params = params
        self._now = now_fn or (lambda: datetime.now(UTC))

    # ----------------------------------------------------------------- helpers
    def domain_for(self, text: str, domain_hint: str | None) -> DomainConfig:
        if domain_hint and domain_hint in self.domains:
            return self.domains[domain_hint]
        return detect_domain(text, self.domains, self.default_domain)

    def candidates_for(self, domain_id: str) -> tuple[list[Entity], list[NameCandidate]]:
        ents = self.repo.list_entities(domain_id)
        cands = [NameCandidate(e.id, e.name, tuple(e.aliases)) for e in ents]
        return ents, cands

    def resolve_entity(
        self,
        u: Understanding,
        text: str,
        ents: list[Entity],
        cands: list[NameCandidate],
    ) -> tuple[Entity | None, float, list[Entity]]:
        """-> (entity or None, confidence, runner-ups for a 'did you mean' question)."""
        by_id = {e.id: e for e in ents}
        if u.entity_id and u.entity_id in by_id:
            return by_id[u.entity_id], u.entity_confidence, []
        if u.entity_name:
            target = normalize(u.entity_name)
            for e in ents:
                if normalize(e.name) == target or any(normalize(a) == target for a in e.aliases):
                    return e, (u.entity_confidence if u.entity_confidence > 0 else 0.8), []
            matches = best_matches(u.entity_name, cands, 3)
            if matches and matches[0][1] >= 0.5:
                conf = min(max(u.entity_confidence, 0.5), matches[0][1])
                return by_id[matches[0][0]], conf, [by_id[m[0]] for m in matches]
        matches = best_matches(text, cands, 3)
        if not matches:
            return None, 0.0, []
        top_id, top = matches[0]
        runners = [by_id[m[0]] for m in matches]
        if len(matches) > 1 and matches[1][1] >= top - AMBIGUITY_MARGIN:
            return None, top, runners
        return by_id[top_id], top, runners

    def alternatives_for(self, entity: Entity, domain: DomainConfig) -> list[AlternativeOut]:
        ents = self.repo.list_entities(domain.id)
        cands = [GeoCandidate(e.id, e.name, e.lat, e.lon, e.current_status, e.confidence) for e in ents]
        alts = nearest_working(
            entity.lat,
            entity.lon,
            cands,
            domain.statuses.good,
            radius_km=domain.alternative.radius_km,
            max_results=domain.alternative.max_results,
            exclude_id=entity.id,
            params=self.params,
        )
        return [AlternativeOut(**a.__dict__) for a in alts]

    def recompute(self, entity_id: str) -> Derived:
        reports = self.repo.reports_for_entity(entity_id)
        obs = [ReportObs(r.status_claimed, r.channel, r.created_at, r.weight) for r in reports]
        derived = derive_status(obs, self._now(), self.params)
        last = max((r.created_at for r in reports), default=None)
        self.repo.update_entity_status(entity_id, derived.status, derived.confidence, last)
        return derived

    def record(
        self,
        entity: Entity,
        status: str,
        channel: Channel,
        reporter_hash: str,
        lang: Lang | None,
        raw_text: str | None,
        note: str | None = None,
        created_at: datetime | None = None,
    ) -> Derived:
        self.repo.add_report(
            Report(
                entity_id=entity.id,
                reporter_hash=reporter_hash,
                channel=channel,
                lang=lang,
                raw_text=raw_text,
                status_claimed=status,
                note=note,
                weight=1.0,
                created_at=created_at or self._now(),
            )
        )
        return self.recompute(entity.id)

    def compose(
        self,
        domain: DomainConfig,
        lang: Lang,
        entity: Entity,
        status_now: str,
        confidence_now: float,
        recorded: bool,
        alternatives: list[AlternativeOut],
    ) -> str:
        label = domain.label(lang, status_now)
        text = domain.t(lang, "recorded" if recorded else "status", name=entity.name, status=label)
        if (
            not recorded
            and status_now not in (UNKNOWN, DISPUTED)
            and confidence_now < self.params.verified_min_confidence
        ):
            text += domain.t(lang, "unverified")
        if alternatives:
            alt = alternatives[0]
            key = "nearest" if alt.verified else "nearest_unverified"
            text += domain.t(lang, key, alt_name=alt.name, minutes=alt.walk_minutes)
        elif not domain.is_good(status_now):
            text += domain.t(lang, "none")
        return text

    # -------------------------------------------------------------- main loop
    def handle(self, msg: InboundMessage) -> OutboundReply:
        key = conversation_key(msg.channel, msg.reporter_hash)
        pending = self.repo.get_pending(key, self._now())
        carry_status: str | None = None
        domain_hint = msg.domain_hint
        lang_hint = msg.lang_hint
        if pending is not None:
            done = self._resolve_pending(pending, msg)
            if done is not None:
                return done
            carry_status = pending.status_claimed
            domain_hint = domain_hint or pending.domain_id
            lang_hint = lang_hint or pending.lang

        domain = self.domain_for(msg.text, domain_hint)
        ents, cands = self.candidates_for(domain.id)
        u = self.understander.understand(msg.text, domain, cands, lang_hint)
        lang: Lang = lang_hint or u.lang

        if u.intent == "help":
            self.repo.clear_pending(key)
            return OutboundReply(
                text=domain.t(lang, "help"),
                intent="help",
                lang=lang,
                domain_id=domain.id,
                understanding_source=u.source,
            )

        entity, conf, runners = self.resolve_entity(u, msg.text, ents, cands)
        status = u.status if u.status in domain.all_statuses else None
        if status is None and carry_status in domain.all_statuses:
            status = carry_status
        attempts = pending.attempts + 1 if pending is not None else 0

        if entity is None:
            ambiguous = len(runners) >= 2 and conf > 0
            if ambiguous or status is not None:
                if attempts >= MAX_FOLLOW_UPS:
                    return self._give_up(key, domain, lang, u.source)
                if ambiguous:
                    return self._ask(
                        key,
                        "choose",
                        domain,
                        lang,
                        msg,
                        status,
                        [r.id for r in runners[:2]],
                        attempts,
                        u.source,
                        fmt={"a": runners[0].name, "b": runners[1].name},
                    )
                return self._ask(
                    key,
                    "need_entity",
                    domain,
                    lang,
                    msg,
                    status,
                    [],
                    attempts,
                    u.source,
                    fmt={"status": domain.label(lang, status or "")},
                )
            self.repo.clear_pending(key)
            return OutboundReply(
                text=domain.t(lang, "unknown"),
                intent="other",
                lang=lang,
                domain_id=domain.id,
                understanding_source=u.source,
            )

        threshold = self.confirm_thresholds.get(msg.channel, 0.6)
        if status is not None and conf < threshold:
            if attempts >= MAX_FOLLOW_UPS:
                return self._give_up(key, domain, lang, u.source)
            return self._ask(
                key,
                "confirm",
                domain,
                lang,
                msg,
                status,
                [entity.id],
                attempts,
                u.source,
                fmt={"name": entity.name},
            )

        self.repo.clear_pending(key)
        return self._answer(domain, lang, entity, status, msg.channel, msg.reporter_hash, msg.text, u.source)

    # ------------------------------------------------------------- follow-ups
    def _ask(
        self,
        key: str,
        kind: PendingKind,
        domain: DomainConfig,
        lang: Lang,
        msg: InboundMessage,
        status: str | None,
        candidate_ids: list[str],
        attempts: int,
        source: str,
        fmt: Mapping[str, object] | None = None,
    ) -> OutboundReply:
        now = self._now()
        self.repo.set_pending(
            PendingQuestion(
                key=key,
                channel=msg.channel,
                domain_id=domain.id,
                lang=lang,
                kind=kind,
                status_claimed=status,
                candidate_ids=candidate_ids,
                raw_text=msg.text,
                attempts=attempts,
                created_at=now,
                expires_at=now + PENDING_TTL,
            )
        )
        template = kind if msg.channel == "voice" else f"{kind}_sms"
        names = [e.name for cid in candidate_ids if (e := self.repo.get_entity(cid)) is not None]
        return OutboundReply(
            text=domain.t(lang, template, **dict(fmt or {})),
            intent="report" if status else "query",
            lang=lang,
            domain_id=domain.id,
            entity_id=candidate_ids[0] if kind == "confirm" else None,
            entity_name=names[0] if kind == "confirm" and names else None,
            needs_confirmation=True,
            pending_kind=kind,
            candidate_ids=candidate_ids,
            candidate_names=names,
            understanding_source=source,  # type: ignore[arg-type]
        )

    def _give_up(self, key: str, domain: DomainConfig, lang: Lang, source: str) -> OutboundReply:
        self.repo.clear_pending(key)
        return OutboundReply(
            text=domain.t(lang, "give_up"),
            intent="other",
            lang=lang,
            domain_id=domain.id,
            understanding_source=source,  # type: ignore[arg-type]
        )

    def _resolve_pending(self, pending: PendingQuestion, msg: InboundMessage) -> OutboundReply | None:
        """Interpret a message as the answer to the open question. None = treat it as a new message."""
        domain = self.domains.get(pending.domain_id) or self.domains[self.default_domain]
        lang: Lang = msg.lang_hint or pending.lang
        text = normalize(msg.text)
        if pending.kind == "confirm" and pending.candidate_ids:
            if text in YES_WORDS:
                return self._finish(pending, domain, lang, msg, pending.candidate_ids[0])
            if text in NO_WORDS:
                return self._cancel(pending, domain, lang, msg)
            return None
        if pending.kind == "choose" and pending.candidate_ids:
            if text.isdigit() and 1 <= int(text) <= len(pending.candidate_ids):
                return self._finish(pending, domain, lang, msg, pending.candidate_ids[int(text) - 1])
            cands = [
                NameCandidate(e.id, e.name, tuple(e.aliases))
                for cid in pending.candidate_ids
                if (e := self.repo.get_entity(cid)) is not None
            ]
            matches = best_matches(msg.text, cands, 2)
            if (
                matches
                and matches[0][1] >= 0.5
                and (len(matches) == 1 or matches[1][1] < matches[0][1] - AMBIGUITY_MARGIN)
            ):
                return self._finish(pending, domain, lang, msg, matches[0][0])
            if text in NO_WORDS:
                return self._cancel(pending, domain, lang, msg)
            return None
        if pending.kind == "need_entity" and text in NO_WORDS:
            self.repo.clear_pending(pending.key)
            return OutboundReply(
                text=domain.t(lang, "cancelled" if msg.channel == "voice" else "cancelled_sms"),
                intent="other",
                lang=lang,
                domain_id=domain.id,
            )
        return None

    def _cancel(
        self, pending: PendingQuestion, domain: DomainConfig, lang: Lang, msg: InboundMessage
    ) -> OutboundReply:
        """ "No" to a guess: keep the status and ask for the place, unless we already asked twice."""
        if pending.status_claimed and pending.attempts + 1 < MAX_FOLLOW_UPS:
            now = self._now()
            self.repo.set_pending(
                pending.model_copy(
                    update={
                        "kind": "need_entity",
                        "candidate_ids": [],
                        "attempts": pending.attempts + 1,
                        "created_at": now,
                        "expires_at": now + PENDING_TTL,
                    }
                )
            )
            return OutboundReply(
                text=domain.t(lang, "cancelled" if msg.channel == "voice" else "cancelled_sms"),
                intent="report",
                lang=lang,
                domain_id=domain.id,
                needs_confirmation=True,
                pending_kind="need_entity",
            )
        self.repo.clear_pending(pending.key)
        return OutboundReply(
            text=domain.t(lang, "cancelled" if msg.channel == "voice" else "cancelled_sms"),
            intent="other",
            lang=lang,
            domain_id=domain.id,
        )

    def _finish(
        self, pending: PendingQuestion, domain: DomainConfig, lang: Lang, msg: InboundMessage, entity_id: str
    ) -> OutboundReply | None:
        entity = self.repo.get_entity(entity_id)
        if entity is None:
            self.repo.clear_pending(pending.key)
            return None
        self.repo.clear_pending(pending.key)
        return self._answer(
            domain,
            lang,
            entity,
            pending.status_claimed,
            msg.channel,
            msg.reporter_hash,
            pending.raw_text,
            "none",
        )

    # ----------------------------------------------------------------- answer
    def _answer(
        self,
        domain: DomainConfig,
        lang: Lang,
        entity: Entity,
        status: str | None,
        channel: Channel,
        reporter_hash: str,
        raw_text: str | None,
        source: str,
    ) -> OutboundReply:
        derived: Derived | None = None
        if status is not None and status in domain.all_statuses:
            derived = self.record(entity, status, channel, reporter_hash, lang, raw_text)
        status_now = derived.status if derived else entity.current_status
        conf_now = derived.confidence if derived else entity.confidence
        entity_now = entity.model_copy(update={"current_status": status_now, "confidence": conf_now})
        alts = [] if domain.is_good(status_now) else self.alternatives_for(entity_now, domain)
        text = self.compose(domain, lang, entity, status_now, conf_now, derived is not None, alts)
        return OutboundReply(
            text=text,
            intent="report" if derived else "query",
            lang=lang,
            domain_id=domain.id,
            entity_id=entity.id,
            entity_name=entity.name,
            status_recorded=status if derived else None,
            current_status=status_now,
            confidence=conf_now,
            alternatives=alts,
            understanding_source=source,  # type: ignore[arg-type]
        )

    def web_report(
        self, entity_id: str, status: str, note: str | None, lang: Lang, reporter_hash: str
    ) -> tuple[Entity, Derived, list[AlternativeOut]] | None:
        entity = self.repo.get_entity(entity_id)
        if entity is None:
            return None
        domain = self.domains[entity.domain_id]
        if status not in domain.all_statuses:
            raise ValueError(f"status must be one of {domain.all_statuses}")
        derived = self.record(entity, status, "web", reporter_hash, lang, None, note=note)
        entity_now = entity.model_copy(
            update={"current_status": derived.status, "confidence": derived.confidence}
        )
        alts = [] if domain.is_good(derived.status) else self.alternatives_for(entity_now, domain)
        return entity_now, derived, alts

    def recompute_all(self) -> int:
        n = 0
        for entity in self.repo.list_entities():
            self.recompute(entity.id)
            n += 1
        return n
