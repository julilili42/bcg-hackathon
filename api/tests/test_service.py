from datetime import UTC, datetime, timedelta

import pytest

from reach.core.domains import DomainConfig
from reach.core.matching import NameCandidate
from reach.core.schemas import Entity, InboundMessage, Lang, Understanding
from reach.core.service import RateLimiter, ReachService, hash_reporter
from reach.storage.repository import Repository


def msg(text: str, channel: str = "sms", lang: Lang | None = None) -> InboundMessage:
    return InboundMessage(channel=channel, reporter_hash="r1", text=text, lang_hint=lang)  # type: ignore[arg-type]


def test_hash_reporter_is_salted_and_stable() -> None:
    a = hash_reporter("+15005550006", "s1")
    assert a == hash_reporter(" +15005550006 ", "s1") and a != hash_reporter("+15005550006", "s2")
    assert "5550006" not in a


def test_report_in_swahili_records_and_offers_alternative(service: ReachService, seeded: Repository) -> None:
    reply = service.handle(msg("Shule imeharibika"))
    assert reply.intent == "report" and reply.lang == "sw"
    assert reply.status_recorded == "broken" and reply.current_status == "broken"
    assert "Shule imeandikwa kama imeharibika" in reply.text
    assert reply.alternatives and reply.alternatives[0].name in {"Kanisa", "Kisarawe Market Tap"}
    assert "dakika" in reply.text
    assert seeded.get_entity("t:shule").current_status == "broken"  # type: ignore[union-attr]
    assert reply.confidence is not None and reply.confidence > 0.3


def test_query_in_english_reports_status_without_recording(service: ReachService, seeded: Repository) -> None:
    reply = service.handle(msg("Is the Soko water point working?"))
    assert reply.intent == "query" and reply.lang == "en"
    assert reply.status_recorded is None
    assert reply.text.startswith("Soko is broken.")
    assert "not verified" in reply.text  # baseline only, nobody has reported yet
    assert "last reported working is" in reply.text and "minutes on foot" in reply.text
    assert len(seeded.reports_for_entity("t:soko")) == 1


def test_unknown_and_help(service: ReachService) -> None:
    assert service.handle(msg("zzz qqq")).intent == "other"
    assert "Sorry" in service.handle(msg("zzz qqq")).text
    assert service.handle(msg("help")).intent == "help"


def test_sms_low_confidence_asks_yes_no_then_records(service: ReachService, seeded: Repository) -> None:
    reply = service.handle(msg("the market is broken"))
    assert reply.pending_kind == "confirm" and reply.entity_name == "Kisarawe Market Tap"
    assert reply.text == "Did you mean Kisarawe Market Tap? Reply YES or NO."
    assert seeded.get_entity("t:market-tap").current_status == "ok"  # type: ignore[union-attr]
    done = service.handle(msg("yes"))
    assert (
        done.status_recorded == "broken" and "recorded as broken" in done.text and done.pending_kind is None
    )
    assert seeded.get_entity("t:market-tap").current_status == "broken"  # type: ignore[union-attr]
    # the question is gone: a bare "yes" now is just an unknown message
    assert service.handle(msg("yes")).intent == "other"


def test_voice_low_confidence_then_press_one_records(service: ReachService, seeded: Repository) -> None:
    reply = service.handle(msg("the market is broken", channel="voice", lang="en"))
    assert reply.pending_kind == "confirm" and "Press one" in reply.text
    done = service.handle(msg("1", channel="voice", lang="en"))
    assert done.status_recorded == "broken" and "recorded as broken" in done.text
    assert seeded.get_entity("t:market-tap").current_status == "broken"  # type: ignore[union-attr]


def test_no_keeps_the_status_and_asks_for_the_place(service: ReachService, seeded: Repository) -> None:
    service.handle(msg("the market is broken"))
    cancelled = service.handle(msg("hapana"))
    assert cancelled.pending_kind == "need_entity" and "full water point name" in cancelled.text
    done = service.handle(msg("Bwawa"))
    assert done.entity_id == "t:bwawa" and done.status_recorded == "broken"
    assert seeded.get_entity("t:market-tap").current_status == "ok"  # type: ignore[union-attr]


def test_status_without_place_asks_which_then_fills_the_slot(
    service: ReachService, seeded: Repository
) -> None:
    ask = service.handle(msg("hakuna maji"))
    assert ask.pending_kind == "need_entity" and ask.lang == "sw"
    assert ask.text == "Umesema haina maji. Kisima gani? Tafadhali tuma jina la kisima au kijiji."
    done = service.handle(msg("Bwawa"))
    assert done.lang == "sw" and done.status_recorded == "empty" and done.entity_id == "t:bwawa"
    assert "Bwawa imeandikwa kama haina maji" in done.text and "Kanisa" in done.text or "Shule" in done.text


def test_gives_up_after_two_follow_ups(service: ReachService) -> None:
    assert service.handle(msg("no water")).pending_kind == "need_entity"
    assert service.handle(msg("somewhere")).pending_kind == "need_entity"
    final = service.handle(msg("still nothing"))
    assert final.pending_kind is None and final.intent == "other" and "could not work that out" in final.text


def test_ambiguous_report_offers_a_choice(service: ReachService, seeded: Repository) -> None:
    for n in (1, 2):
        seeded.upsert_entity(
            Entity(
                id=f"t:marui{n}",
                domain_id="water",
                name=f"Marui Borehole {n}",
                lat=-7.36 - n / 100,
                lon=38.77,
                source="demo",
                external_id=f"m{n}",
            )
        )
    ask = service.handle(msg("Marui borehole is dry"))
    assert ask.pending_kind == "choose" and ask.candidate_ids == ["t:marui1", "t:marui2"]
    assert ask.text == "Did you mean Marui Borehole 1 or Marui Borehole 2? Reply 1 or 2."
    done = service.handle(msg("2"))
    assert done.entity_id == "t:marui2" and done.status_recorded == "empty"
    assert seeded.get_entity("t:marui1").current_status == "unknown"  # type: ignore[union-attr]


def test_ambiguous_query_is_a_choice_without_recording(service: ReachService, seeded: Repository) -> None:
    for n in (1, 2):
        seeded.upsert_entity(
            Entity(
                id=f"t:marui{n}",
                domain_id="water",
                name=f"Marui Borehole {n}",
                lat=-7.36,
                lon=38.77 + n / 100,
                source="demo",
                external_id=f"m{n}",
                current_status="ok",
                confidence=0.5,
            )
        )
    ask = service.handle(msg("Is Marui borehole working?"))
    assert ask.pending_kind == "choose" and ask.intent == "query"
    answer = service.handle(msg("Marui Borehole 1"))
    assert answer.intent == "query" and answer.entity_id == "t:marui1" and answer.status_recorded is None
    assert len(seeded.reports_for_entity("t:marui1")) == 0


def test_new_complete_report_replaces_an_open_question(service: ReachService, seeded: Repository) -> None:
    service.handle(msg("no water"))
    done = service.handle(msg("Kanisa imeharibika"))
    assert done.entity_id == "t:kanisa" and done.status_recorded == "broken"
    assert seeded.get_pending("sms:r1", datetime.now(UTC)) is None


def test_open_question_expires(seeded: Repository) -> None:
    from reach.brain.keywords import KeywordUnderstander
    from reach.core.domains import load_domains

    clock = {"now": datetime(2026, 10, 16, 12, 0, tzinfo=UTC)}
    svc = ReachService(seeded, load_domains(), KeywordUnderstander(), now_fn=lambda: clock["now"])
    assert svc.handle(msg("the market is broken")).pending_kind == "confirm"
    clock["now"] += timedelta(minutes=11)
    late = svc.handle(msg("yes"))
    assert late.intent == "other" and late.pending_kind is None


def test_conflict_becomes_disputed_then_resolves(service: ReachService) -> None:
    service.handle(InboundMessage(channel="sms", reporter_hash="a", text="Kanisa imeharibika"))
    second = service.handle(InboundMessage(channel="sms", reporter_hash="b", text="Kanisa inafanya kazi"))
    assert second.current_status == "disputed"
    assert "zinazopingana" in second.text
    third = service.handle(
        InboundMessage(channel="voice", reporter_hash="c", text="Kanisa imeharibika", lang_hint="sw")
    )
    assert third.current_status == "broken"


def test_health_domain_detected_from_hints(service: ReachService, seeded: Repository) -> None:
    reply = service.handle(msg("Zahanati Msanga imefungwa"))
    assert reply.domain_id == "health" and reply.status_recorded == "closed"
    assert "Msanga Dispensary imeandikwa kama imefungwa" in reply.text
    assert "Hakuna kituo" in reply.text  # Mzenga is ~40 km away, outside the 25 km radius
    assert seeded.get_entity("t:msanga").current_status == "closed"  # type: ignore[union-attr]


def test_web_report_validates_status(service: ReachService) -> None:
    with pytest.raises(ValueError):
        service.web_report("t:shule", "closed", None, "en", "w")
    assert service.web_report("missing", "broken", None, "en", "w") is None
    result = service.web_report("t:shule", "empty", "pump handle gone", "en", "w")
    assert result is not None and result[1].status == "empty" and result[2]


def test_rate_limiter_sliding_window() -> None:
    clock = [0.0]
    limiter = RateLimiter(2, 10, clock=lambda: clock[0])
    assert limiter.allow("k") and limiter.allow("k") and not limiter.allow("k")
    clock[0] = 11.0
    assert limiter.allow("k")


class StubUnderstander:
    name = "stub"

    def __init__(self, u: Understanding) -> None:
        self.u = u

    def understand(
        self, text: str, domain: DomainConfig, candidates: list[NameCandidate], lang_hint: Lang | None
    ) -> Understanding:
        return self.u


def test_claude_style_name_resolution(seeded: Repository, service: ReachService) -> None:
    stub = StubUnderstander(
        Understanding(
            intent="report",
            entity_name="shule",
            entity_confidence=0.95,
            status="empty",
            lang="en",
            source="claude",
        )
    )
    svc = ReachService(seeded, service.domains, stub)
    reply = svc.handle(msg("whatever the caller said"))
    assert reply.entity_id == "t:shule" and reply.status_recorded == "empty"
    assert reply.understanding_source == "claude"
    fuzzy = StubUnderstander(
        Understanding(
            intent="query", entity_name="Kisarawe Market", entity_confidence=0.7, lang="en", source="claude"
        )
    )
    reply2 = ReachService(seeded, service.domains, fuzzy).handle(msg("..."))
    assert reply2.entity_id == "t:market-tap" and reply2.intent == "query"


def test_recompute_all_touches_every_entity(service: ReachService) -> None:
    assert service.recompute_all() == 7
    assert isinstance(service.recompute("t:shule").confidence, float)
    assert datetime.now(UTC) is not None
