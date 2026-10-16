import os
from typing import Any

import pytest

from reach.brain.claude import OUTPUT_SCHEMA, ClaudeUnderstander, build_system_prompt
from reach.brain.keywords import KeywordUnderstander
from reach.core.domains import load_domains
from reach.core.matching import NameCandidate

CANDS = [NameCandidate("a", "Shule", ("Kisima cha Shule",)), NameCandidate("b", "Kanisa")]


def make(caller: Any) -> ClaudeUnderstander:
    return ClaudeUnderstander("key", "claude-opus-5-5", 4.0, KeywordUnderstander(), caller=caller)


def test_system_prompt_lists_candidates_and_statuses() -> None:
    prompt = build_system_prompt(load_domains()["water"], CANDS)
    assert "- Shule (also: Kisima cha Shule)" in prompt and "broken = broken / imeharibika" in prompt
    assert set(OUTPUT_SCHEMA["required"]) == set(OUTPUT_SCHEMA["properties"])


def test_valid_claude_answer_is_used() -> None:
    def caller(system: str, text: str) -> dict[str, Any]:
        return {
            "intent": "report",
            "entity_name": "Shule",
            "entity_confidence": 0.93,
            "status": "broken",
            "lang": "sw",
            "place_hint": None,
        }

    u = make(caller).understand("kisima shule imeharibika", load_domains()["water"], CANDS, None)
    assert u.source == "claude" and u.entity_name == "Shule" and u.status == "broken" and u.lang == "sw"


def test_invalid_status_is_dropped_and_lang_hint_wins() -> None:
    def caller(system: str, text: str) -> dict[str, Any]:
        return {
            "intent": "report",
            "entity_name": "Shule",
            "entity_confidence": 0.9,
            "status": "flooded",
            "lang": "sw",
            "place_hint": "Kisarawe",
        }

    u = make(caller).understand("...", load_domains()["water"], CANDS, "en")
    assert u.status is None and u.lang == "en" and u.place_hint == "Kisarawe"


def test_failure_falls_back_to_keywords() -> None:
    def caller(system: str, text: str) -> dict[str, Any]:
        raise TimeoutError("slow")

    u = make(caller).understand("Kanisa imeharibika", load_domains()["water"], CANDS, None)
    assert u.source == "keywords" and u.entity_id == "b" and u.status == "broken"


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE"), reason="set RUN_LIVE=1 with ANTHROPIC_API_KEY for a live call"
)
def test_live_call() -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    u = ClaudeUnderstander(api_key, "claude-opus-5-5", 8.0, KeywordUnderstander()).understand(
        "kisima cha shule hakifanyi kazi", load_domains()["water"], CANDS, None
    )
    assert u.source == "claude" and u.entity_name == "Shule" and u.status == "broken"
