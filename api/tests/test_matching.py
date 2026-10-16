from reach.core.matching import (
    NameCandidate,
    best_matches,
    detect_intent,
    detect_lang,
    detect_status,
    is_question,
    normalize,
    score_candidate,
)

CANDS = [
    NameCandidate("a", "Shule", ("Kisima cha Shule",)),
    NameCandidate("b", "Kanisa"),
    NameCandidate("c", "Marui Borehole 1"),
    NameCandidate("d", "Marui Borehole 2"),
    NameCandidate("e", "Kisarawe Market Tap"),
]
WATER_KW = {
    "broken": ["broken", "imeharibika", "haifanyi kazi"],
    "empty": ["empty", "haina maji", "no water"],
    "ok": ["working", "inafanya kazi"],
}


def test_normalize_strips_accents_and_punctuation() -> None:
    assert normalize("  Kísima, cha   SHULE! ") == "kisima cha shule"


def test_exact_alias_scores_one() -> None:
    assert score_candidate("kisima cha shule hakifanyi kazi", CANDS[0]) == 1.0


def test_fuzzy_prefix_tolerates_speech_errors() -> None:
    top = best_matches("kanisah is broken", CANDS, 1)
    assert top and top[0][0] == "b" and top[0][1] >= 0.8


def test_ambiguous_ward_names_tie() -> None:
    matches = best_matches("Marui borehole is dry", CANDS, 3)
    assert matches[0][1] == matches[1][1]
    assert {matches[0][0], matches[1][0]} == {"c", "d"}


def test_partial_multiword_name_gets_partial_score() -> None:
    matches = best_matches("the market is broken", CANDS, 1)
    assert matches and matches[0][0] == "e"
    assert 0.2 < matches[0][1] < 0.6


def test_detect_status_prefers_longest_keyword() -> None:
    from reach.core.domains import load_domains

    kw = load_domains()["water"].status_keywords
    assert detect_status("Kisima cha Shule hakifanyi kazi", kw) == "broken"
    assert detect_status("Kisima cha Shule hakina maji", kw) == "empty"
    assert detect_status("Shule kinafanya kazi", kw) == "ok"
    assert detect_status("the pump isn't working", kw) == "broken"
    assert detect_status("Shule haina maji", WATER_KW) == "empty"
    assert detect_status("Shule imeharibika", WATER_KW) == "broken"
    assert detect_status("where is water", WATER_KW) is None


def test_detect_lang() -> None:
    assert detect_lang("Shule imeharibika") == "sw"
    assert detect_lang("The Shule well is broken") == "en"


def test_detect_intent() -> None:
    assert detect_intent("help", False, False) == "help"
    assert detect_intent("Shule imeharibika", True, True) == "report"
    assert detect_intent("where is water near Soko", False, True) == "query"
    assert detect_intent("blah", False, False) == "other"


def test_questions_do_not_count_as_reports() -> None:
    assert is_question("Is the Soko water point working?")
    assert is_question("kisima cha Shule kiko wapi")
    assert not is_question("Shule imeharibika")
    assert detect_intent("Is the Soko water point working?", True, True) == "query"
