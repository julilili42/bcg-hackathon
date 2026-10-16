"""Twilio voice and SMS webhooks. State for the voice confirmation step travels in the action URL."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response

from reach.channels import twiml
from reach.channels.twilio_auth import public_base, twilio_form
from reach.core.schemas import InboundMessage, Interaction, Lang, OutboundReply
from reach.core.service import ReachService, hash_reporter

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["twilio"])

STT_LANG: dict[Lang, str] = {"sw": "sw-TZ", "en": "en-US"}
Form = Annotated[dict[str, str], Depends(twilio_form)]
MAX_RETRIES = 1


def _xml(body: str) -> Response:
    return Response(content=body, media_type="text/xml")


def _lang(raw: str | None) -> Lang:
    return "en" if raw == "en" else "sw"


def _speak(request: Request, text: str, lang: Lang) -> str:
    tts = request.app.state.tts
    path = tts.synthesize(text, lang)
    if path is not None:
        base = public_base(request, request.app.state.settings)
        return twiml.play(f"{base}/api/audio/{path.name}")
    # Twilio has no Swahili voice: for sw we let the default voice read the text rather than
    # risk an unsupported language attribute that would fail the call.
    return twiml.say(text, STT_LANG["en"] if lang == "en" else None)


def _hints(service: ReachService, domain_id: str) -> str:
    ents = service.repo.list_entities(domain_id)
    words: list[str] = []
    for e in ents:
        if not e.aliases:
            continue
        words.append(e.name)
        words.extend(a for a in e.aliases if not any(ch.isdigit() for ch in a) and len(a.split()) <= 3)
    return ", ".join(dict.fromkeys(words))[:500]


VOICE_BASE = "/api/voice"


def _gather_prompt(
    request: Request, prompt: str, lang: Lang, domain_id: str, retry: int = 0, base: str = VOICE_BASE
) -> str:
    service: ReachService = request.app.state.service
    action = f"{base}/handle?" + urlencode({"lang": lang, "domain": domain_id, "retry": retry})
    return twiml.gather(
        _speak(request, prompt, lang),
        action,
        language=STT_LANG[lang],
        hints=_hints(service, domain_id) or None,
    )


def _log(
    request: Request, channel: str, sender_hash: str, body: str, reply: OutboundReply, started: float
) -> None:
    service: ReachService = request.app.state.service
    service.repo.log_interaction(
        Interaction(
            channel="voice" if channel == "voice" else "sms",
            sender_hash=sender_hash,
            lang=reply.lang,
            body=body,
            reply=reply.text,
            intent=reply.intent,
            entity_id=reply.entity_id,
            latency_ms=int((time.perf_counter() - started) * 1000),
            created_at=datetime.now(UTC),
        )
    )
    log.info(
        '{"channel": "%s", "lang": "%s", "intent": "%s", "entity_id": "%s", "latency_ms": %d, "src": "%s"}',
        channel,
        reply.lang,
        reply.intent,
        reply.entity_id,
        int((time.perf_counter() - started) * 1000),
        reply.understanding_source,
    )


def _sender_hash(request: Request, form: dict[str, str]) -> str:
    return hash_reporter(form.get("From", "anonymous"), request.app.state.settings.reporter_salt)


def voice_start_impl(
    request: Request, form: dict[str, str], base: str = VOICE_BASE, lang: str = "sw"
) -> Response:
    """Greeting in Swahili by default (press 2 for English) or straight in English with ?lang=en."""
    service: ReachService = request.app.state.service
    domain = service.domains[service.default_domain]
    current: Lang = _lang(lang)
    prompt = _gather_prompt(request, domain.t(current, "greet"), current, domain.id, base=base)
    return _xml(twiml.response(prompt))


@router.post("/voice")
def voice_start(request: Request, form: Form, lang: str = Query(default="sw")) -> Response:
    return voice_start_impl(request, form, lang=lang)


def _render(
    request: Request, reply: OutboundReply, lang: Lang, domain_id: str, base: str = VOICE_BASE
) -> Response:
    """Speak the reply; when a follow-up is open, gather the answer instead of hanging up."""
    service: ReachService = request.app.state.service
    if reply.pending_kind is not None:
        action = f"{base}/answer?" + urlencode({"lang": lang, "domain": domain_id})
        if reply.pending_kind == "need_entity":
            hints = _hints(service, domain_id) or None
        else:
            hints = ", ".join(reply.candidate_names)[:500] or None
        return _xml(
            twiml.response(
                twiml.gather(_speak(request, reply.text, lang), action, language=STT_LANG[lang], hints=hints)
            )
        )
    return _xml(twiml.response(_speak(request, reply.text, lang), twiml.hangup()))


def voice_handle_impl(
    request: Request,
    form: dict[str, str],
    lang: str,
    domain: str,
    retry: int,
    base: str = VOICE_BASE,
    limit: bool = True,
) -> Response:
    started = time.perf_counter()
    service: ReachService = request.app.state.service
    current: Lang = _lang(lang)
    domain_id = domain if domain in service.domains else service.default_domain
    cfg = service.domains[domain_id]

    if form.get("Digits") == "2" and current == "sw":
        return _xml(twiml.response(_gather_prompt(request, cfg.t("en", "greet"), "en", domain_id, base=base)))

    text = form.get("SpeechResult", "").strip()
    if not text:
        if retry < MAX_RETRIES:
            return _xml(
                twiml.response(
                    _gather_prompt(request, cfg.t(current, "retry"), current, domain_id, retry + 1, base=base)
                )
            )
        return _xml(twiml.response(_speak(request, cfg.t(current, "goodbye"), current), twiml.hangup()))

    sender = _sender_hash(request, form)
    if limit and not request.app.state.limiter.allow(sender):
        return _xml(twiml.response(_speak(request, cfg.t(current, "too_many"), current), twiml.hangup()))

    reply = service.handle(
        InboundMessage(channel="voice", reporter_hash=sender, text=text, lang_hint=current)
    )
    _log(request, "voice", sender, text, reply, started)
    return _render(request, reply, current, reply.domain_id, base=base)


@router.post("/voice/handle")
def voice_handle(
    request: Request,
    form: Form,
    lang: str = Query(default="sw"),
    domain: str = Query(default=""),
    retry: int = Query(default=0),
) -> Response:
    return voice_handle_impl(request, form, lang, domain, retry)


def voice_answer_impl(
    request: Request, form: dict[str, str], lang: str, domain: str, retry: int, base: str = VOICE_BASE
) -> Response:
    """The caller answered a follow-up: a key press (1/2) or speech (yes/no, a name, a full sentence)."""
    started = time.perf_counter()
    service: ReachService = request.app.state.service
    current: Lang = _lang(lang)
    domain_id = domain if domain in service.domains else service.default_domain
    cfg = service.domains[domain_id]
    text = (form.get("Digits") or form.get("SpeechResult", "")).strip()
    if not text:
        if retry < MAX_RETRIES:
            action = "/api/voice/answer?" + urlencode(
                {"lang": current, "domain": domain_id, "retry": retry + 1}
            )
            prompt = _speak(request, cfg.t(current, "retry"), current)
            return _xml(twiml.response(twiml.gather(prompt, action, language=STT_LANG[current])))
        return _xml(twiml.response(_speak(request, cfg.t(current, "goodbye"), current), twiml.hangup()))
    sender = _sender_hash(request, form)
    reply = service.handle(
        InboundMessage(
            channel="voice", reporter_hash=sender, text=text, lang_hint=current, domain_hint=domain_id
        )
    )
    _log(request, "voice", sender, text, reply, started)
    return _render(request, reply, current, reply.domain_id, base=base)


@router.post("/voice/answer")
def voice_answer(
    request: Request,
    form: Form,
    lang: str = Query(default="sw"),
    domain: str = Query(default=""),
    retry: int = Query(default=0),
) -> Response:
    return voice_answer_impl(request, form, lang, domain, retry)


def sms_impl(request: Request, form: dict[str, str], limit: bool = True) -> Response:
    started = time.perf_counter()
    service: ReachService = request.app.state.service
    text = form.get("Body", "").strip()[:500]
    sender = _sender_hash(request, form)
    default_cfg = service.domains[service.default_domain]
    if not text:
        return _xml(twiml.response(twiml.message(default_cfg.t("en", "help"))))
    if limit and not request.app.state.limiter.allow(sender):
        return _xml(twiml.response(twiml.message(default_cfg.t("en", "too_many"))))
    reply = service.handle(InboundMessage(channel="sms", reporter_hash=sender, text=text))
    _log(request, "sms", sender, text, reply, started)
    return _xml(twiml.response(twiml.message(reply.text)))


@router.post("/sms")
def sms(request: Request, form: Form) -> Response:
    return sms_impl(request, form)


@router.get("/audio/{name}")
def audio(request: Request, name: str) -> Response:
    audio_dir: Path = request.app.state.settings.audio_dir
    path = audio_dir / Path(name).name
    if not path.is_file() or path.suffix != ".wav":
        return Response(status_code=404)
    return Response(content=path.read_bytes(), media_type="audio/wav")
