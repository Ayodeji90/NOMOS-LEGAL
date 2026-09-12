"""Per-jurisdiction v2 flags (E1): only listed ids use the hybrid path."""

from app.core.flags import parse_v2_jurisdictions, uses_v2


def test_empty_flag_means_all_legacy() -> None:
    assert parse_v2_jurisdictions("") == set()
    assert not uses_v2("za", "")


def test_za_only_scope() -> None:
    assert uses_v2("za", "za")
    assert uses_v2("ZA", "za")
    assert not uses_v2("gb", "za")
    assert not uses_v2("ng", "za")


def test_multi_flag_parsing() -> None:
    assert parse_v2_jurisdictions("za, ng") == {"za", "ng"}
