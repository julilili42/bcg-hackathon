"""Understanding: Claude Opus 5.5 with a deterministic keyword fallback (ADR 0005)."""

from __future__ import annotations

from reach.brain.claude import ClaudeUnderstander
from reach.brain.keywords import KeywordUnderstander
from reach.core.service import Understander
from reach.settings import Settings


def build_understander(settings: Settings) -> Understander:
    keywords = KeywordUnderstander()
    if not settings.claude_enabled:
        return keywords
    return ClaudeUnderstander(
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
        timeout_s=settings.claude_timeout_s,
        fallback=keywords,
        use_server_fallbacks=settings.claude_fallbacks,
    )


__all__ = ["ClaudeUnderstander", "KeywordUnderstander", "build_understander"]
