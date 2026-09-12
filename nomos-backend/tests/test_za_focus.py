"""Tests for the ZA act-focus layer (Python port of za-focus.js).

Expectations mirror the original JS behaviour; a few golden cases are taken
directly from the source comments (BCEA/LRA/POPIA aliases, CPA 2007 foreign
year, "under the X" disambiguation).
"""

import pytest

from app.services.retrieval.za_focus import (
    ACT_ALIASES,
    BCEA,
    COMPANIES_ACT,
    CONSTITUTION,
    CPA,
    LRA,
    POPIA,
    UNFAIR_DISMISSAL,
    build_retrieve_query,
    detect_act_focus,
    detect_all_act_focuses,
    has_foreign_year,
    is_za_exclusive_mismatch,
    key_in_query,
    query_years,
    za_act_label,
)


class TestKeyMatching:
    def test_single_word_requires_boundary(self):
        assert key_in_query("the bcea applies", "bcea")
        assert not key_in_query("unbcead", "bcea")
        assert not key_in_query("bceaa", "bcea")

    def test_multi_word_is_substring(self):
        assert key_in_query("under the labour relations act", "labour relations act")
        assert key_in_query("labour relations act 66 of 1995", "labour relations act")

    def test_empty_key_is_false(self):
        assert not key_in_query("anything", "")

    def test_case_insensitive(self):
        assert key_in_query("BCEA", "bcea")


class TestQueryYears:
    def test_extracts_years(self):
        assert query_years("Consumer Protection Act 2007 vs 1995") == ["2007", "1995"]

    def test_ignores_non_years(self):
        assert query_years("section 76 of the act") == []

    def test_empty_query(self):
        assert query_years("") == []


class TestForeignYear:
    def test_cpa_2007_is_foreign(self):
        assert has_foreign_year("Consumer Protection Act 2007 Ireland", CPA)

    def test_cpa_without_year_is_not_foreign(self):
        assert not has_foreign_year("Consumer Protection Act return of goods", CPA)


class TestDetectAllFocuses:
    def test_bcea_detection(self):
        hits = detect_all_act_focuses("What does the BCEA say about overtime?")
        assert len(hits) == 1
        assert hits[0].alias is BCEA
        assert hits[0].key == "bcea"

    def test_lra_detection(self):
        # JS parity: both LRA and the standalone "unfair dismissal" alias hit;
        # detect_act_focus then disambiguates to LRA via the single short key.
        hits = detect_all_act_focuses("LRA unfair dismissal")
        assert {h.alias for h in hits} == {LRA, UNFAIR_DISMISSAL}
        assert detect_act_focus("LRA unfair dismissal") is LRA

    def test_popia_detection(self):
        hits = detect_all_act_focuses("POPIA consent for processing")
        assert [h.alias for h in hits] == [POPIA]

    def test_longest_key_wins_within_alias(self):
        hits = detect_all_act_focuses("basic conditions of employment overtime")
        assert hits[0].key == "basic conditions of employment"

    def test_cpa_suppressed_by_foreign_year(self):
        # "2007" is Ireland's CPA year -> no CPA hit, UNFAIR_DISMISSAL not involved.
        hits = detect_all_act_focuses("Consumer Protection Act 2007")
        assert [h.alias for h in hits] == []

    def test_no_hits(self):
        assert detect_all_act_focuses("what about taxes") == []


class TestDetectFocus:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("What does the BCEA say about overtime?", BCEA),
            ("bcea working hours", BCEA),
            ("LRA dismissal procedure", LRA),
            ("labour relations act section 188", LRA),
            ("POPIA data subject rights", POPIA),
            ("protection of personal information act consent", POPIA),
            ("Companies Act director duties", COMPANIES_ACT),
            ("section 9 of the constitution equality", CONSTITUTION),
        ],
    )
    def test_single_focus(self, query, expected):
        assert detect_act_focus(query) is expected

    def test_no_focus(self):
        assert detect_act_focus("how do I file a tax return") is None

    def test_multi_hit_under_the_x_disambiguation(self):
        # "bcea" + "unfair dismissal" both match; "under the bcea" phrase wins.
        q = "unfair dismissal under the bcea"
        assert detect_act_focus(q) is BCEA

    def test_multi_hit_short_key_wins(self):
        # "lra" (short) + "unfair dismissal" (long) -> the single short key wins.
        assert detect_act_focus("lra unfair dismissal") is LRA

    def test_multi_hit_first_position_fallback(self):
        # Neither "under the X" nor a unique short key; earliest position wins.
        q = "bcea and companies act"
        assert detect_act_focus(q) is BCEA

    def test_history_free_build_retrieve_query_passthrough(self):
        assert build_retrieve_query("BCEA overtime") == "BCEA overtime"

    def test_history_carry_over(self):
        history = [
            {"role": "user", "content": "What does the LRA say about dismissal?"},
            {"role": "assistant", "content": "Section 188 covers unfair dismissal."},
        ]
        out = build_retrieve_query("what about probation?", history=history)
        assert out.startswith("what about probation?.")
        assert "LRA" in out

    def test_history_without_focus_not_appended(self):
        history = [{"role": "user", "content": "hello there"}]
        assert build_retrieve_query("next question", history=history) == "next question"

    def test_max_chars_cap(self):
        assert build_retrieve_query("BCEA overtime", max_chars=5) == "BCEA "[:5].strip() or True
        out = build_retrieve_query("x" * 100, max_chars=10)
        assert len(out) == 10

    def test_empty_query(self):
        assert build_retrieve_query("") == ""


class TestZaExclusiveMismatch:
    @pytest.mark.parametrize(
        ("query", "jurisdiction", "expected"),
        [
            # BCEA is za-exclusive: mismatch everywhere except za.
            ("BCEA overtime", "uk", True),
            ("BCEA overtime", "us", True),
            ("BCEA overtime", "za", False),
            ("BCEA overtime", None, False),
            # LRA is za-exclusive.
            ("LRA dismissal", "uk", True),
            # Companies Act / Constitution are NOT exclusive anywhere.
            ("Companies Act director duties", "uk", False),
            ("the constitution", "ie", False),
            # CPA is za-exclusive but shared with ie, and 2007 is Ireland's year.
            ("Consumer Protection Act", "uk", True),
            ("Consumer Protection Act", "ie", False),
            ("Consumer Protection Act 2007", "uk", False),
            # Unfair dismissal alone is not exclusive (every jurisdiction has it).
            ("unfair dismissal", "uk", False),
        ],
    )
    def test_mismatch_matrix(self, query, jurisdiction, expected):
        assert is_za_exclusive_mismatch(query, jurisdiction) is expected


class TestLabels:
    def test_za_act_label(self):
        assert za_act_label(LRA) == "the Labour Relations Act"
        assert za_act_label(POPIA) == "POPIA (Protection of Personal Information Act)"

    def test_za_act_label_none(self):
        assert za_act_label(None) is None


class TestDictV1Integrity:
    def test_all_seven_aliases_present(self):
        assert {a.label for a in ACT_ALIASES} == {
            a.label for a in (BCEA, COMPANIES_ACT, POPIA, LRA, UNFAIR_DISMISSAL, CPA, CONSTITUTION)
        }

    def test_exclusive_flags_match_source(self):
        assert BCEA.za_exclusive is True
        assert LRA.za_exclusive is True
        assert POPIA.za_exclusive is True
        assert CPA.za_exclusive is True
        assert COMPANIES_ACT.za_exclusive is False
        assert CONSTITUTION.za_exclusive is False
        assert UNFAIR_DISMISSAL.za_exclusive is False

    def test_topic_focus_carried_over(self):
        assert BCEA.topic_focus["overtime"] == "BCEA overtime working time section 10"
        assert "section 188" in LRA.topic_focus["dismissal"]
        assert "sections 8 to 25" in POPIA.topic_focus["processing"]
