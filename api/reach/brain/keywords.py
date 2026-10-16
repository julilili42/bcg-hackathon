"""Deterministic understanding. The demo must work on this alone."""

from __future__ import annotations

from reach.core.domains import DomainConfig
from reach.core.matching import (
    NameCandidate,
    best_matches,
    detect_intent,
    detect_lang,
    detect_status,
    is_question,
)
from reach.core.schemas import Lang, Understanding

AMBIGUITY_MARGIN = 0.05


class KeywordUnderstander:
    name = "keywords"

    def understand(
        self,
        text: str,
        domain: DomainConfig,
        candidates: list[NameCandidate],
        lang_hint: Lang | None,
    ) -> Understanding:
        status = None if is_question(text) else detect_status(text, domain.status_keywords)
        matches = best_matches(text, candidates, 3)
        entity_id: str | None = None
        confidence = 0.0
        if matches:
            top_id, top = matches[0]
            confidence = top
            ambiguous = len(matches) > 1 and matches[1][1] >= top - AMBIGUITY_MARGIN
            if not ambiguous:
                entity_id = top_id
        lang = lang_hint or detect_lang(text)
        intent = detect_intent(text, status is not None, entity_id is not None)
        return Understanding(
            intent=intent,
            entity_id=entity_id,
            entity_confidence=confidence,
            status=status,
            lang=lang,
            source="keywords",
        )
