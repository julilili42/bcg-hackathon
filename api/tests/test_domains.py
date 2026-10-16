from reach.core.domains import detect_domain, load_domains


def test_both_domains_load_with_complete_templates() -> None:
    domains = load_domains()
    assert set(domains) == {"water", "health"}
    for cfg in domains.values():
        for lang in ("sw", "en"):
            keys = (
                "greet",
                "unknown",
                "recorded",
                "status",
                "nearest",
                "nearest_unverified",
                "none",
                "help",
                "retry",
                "goodbye",
                "too_many",
                "confirm",
                "confirm_sms",
                "choose",
                "choose_sms",
                "need_entity",
                "need_entity_sms",
                "cancelled",
                "cancelled_sms",
                "give_up",
            )
            for key in keys:
                assert cfg.t(lang, key, name="X", status="y", alt_name="Z", minutes=5, a="A", b="B"), (
                    lang,
                    key,
                )
        assert cfg.label("sw", "unknown") and cfg.label("en", "disputed")
        assert cfg.all_statuses == [*cfg.statuses.good, *cfg.statuses.bad]


def test_detect_domain_by_hints() -> None:
    domains = load_domains()
    assert detect_domain("Zahanati Msanga imefungwa", domains, "water").id == "health"
    assert detect_domain("Kisima cha Shule hakifanyi kazi", domains, "water").id == "water"
    assert detect_domain("blah blah", domains, "water").id == "water"


def test_domain_out_is_serializable() -> None:
    out = load_domains()["health"].to_out()
    assert out.good_statuses == ["open"] and "closed" in out.bad_statuses
