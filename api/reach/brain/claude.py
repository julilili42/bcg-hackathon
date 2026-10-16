"""Claude understanding step: structured JSON output, low effort, hard timeout, keyword fallback.

The prompt puts the stable part first (role, domain, candidate list) and the utterance last.
Any exception or refusal falls back to keywords so the caller always gets an answer.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, cast

from reach.core.domains import DomainConfig
from reach.core.matching import NameCandidate
from reach.core.schemas import Intent, Lang, Understanding
from reach.core.service import Understander

log = logging.getLogger(__name__)

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["report", "query", "help", "other"]},
        "entity_name": {"type": ["string", "null"]},
        "entity_confidence": {"type": "number"},
        "status": {"type": ["string", "null"]},
        "lang": {"type": "string", "enum": ["sw", "en"]},
        "place_hint": {"type": ["string", "null"]},
    },
    "required": ["intent", "entity_name", "entity_confidence", "status", "lang", "place_hint"],
    "additionalProperties": False,
}

Caller = Callable[[str, str], dict[str, Any]]


def build_system_prompt(
    domain: DomainConfig, candidates: list[NameCandidate], max_candidates: int = 400
) -> str:
    statuses = ", ".join(
        f"{s} = {domain.label('en', s)} / {domain.label('sw', s)}" for s in domain.all_statuses
    )
    lines = []
    for cand in candidates[:max_candidates]:
        alias = f" (also: {', '.join(cand.aliases)})" if cand.aliases else ""
        lines.append(f"- {cand.name}{alias}")
    return (
        "You read one message sent to Reach, a community hotline for the status of "
        f"{domain.names['en']}s ({domain.names['sw']} in Swahili). Messages arrive by SMS or as "
        "speech-to-text from a phone call, in Swahili or English, often garbled.\n"
        f"Statuses: {statuses}. A report names a {domain.names['en']} and claims a status. "
        "A query asks about a place or the nearest working one and claims no status. "
        "help = the sender asks what to do. other = none of these.\n"
        "Match the named place loosely against the known list below (spelling, case, partial words, "
        "speech-recognition errors). entity_name must be copied exactly from the list or be null. "
        "entity_confidence is 0 to 1. status must be one of the status keys or null. lang is the "
        "language the sender wrote or spoke. place_hint is a village or ward if mentioned, else null.\n"
        f"Known {domain.names['en']}s:\n" + "\n".join(lines)
    )


class ClaudeUnderstander:
    name = "claude"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float,
        fallback: Understander,
        use_server_fallbacks: bool = True,
        caller: Caller | None = None,
        max_tokens: int = 400,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.fallback = fallback
        self.use_server_fallbacks = use_server_fallbacks
        self.max_tokens = max_tokens
        self._caller = caller or self._call_api
        self._client: Any = None

    def _client_or_create(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout_s, max_retries=0)
        return self._client

    def _call_api(self, system: str, text: str) -> dict[str, Any]:
        client = self._client_or_create()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": text}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        }
        if self.use_server_fallbacks:
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        else:
            response = client.messages.create(**kwargs)
        if response.stop_reason == "refusal":
            raise RuntimeError("claude refused the request")
        body = next(block.text for block in response.content if block.type == "text")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("unexpected response shape")
        return data

    def understand(
        self,
        text: str,
        domain: DomainConfig,
        candidates: list[NameCandidate],
        lang_hint: Lang | None,
    ) -> Understanding:
        system = build_system_prompt(domain, candidates)
        try:
            data = self._caller(system, text)
            status = data.get("status")
            if status is not None and status not in domain.all_statuses:
                status = None
            lang_raw = data.get("lang")
            lang: Lang = lang_hint or ("sw" if lang_raw == "sw" else "en")
            intent_raw = data.get("intent")
            intent: Intent = (
                cast(Intent, intent_raw) if intent_raw in ("report", "query", "help", "other") else "other"
            )
            name = data.get("entity_name")
            return Understanding(
                intent=intent,
                entity_name=str(name) if name else None,
                entity_confidence=float(data.get("entity_confidence") or 0.0),
                status=status,
                lang=lang,
                place_hint=str(data["place_hint"]) if data.get("place_hint") else None,
                source="claude",
            )
        except Exception as exc:  # noqa: BLE001 - any failure must degrade to keywords
            log.warning("claude understanding failed, using keywords: %s", exc)
            return self.fallback.understand(text, domain, candidates, lang_hint)
