"""Tests for the synonym-dict loader and the ZA dict v1 (BCEA/LRA/POPIA aliases)."""

import json
from pathlib import Path

import pytest

from app.services.retrieval.synonyms import (
    JsonFileSynonymDictLoader,
    SynonymDictError,
    SynonymDictLoader,
    clear_synonym_cache,
    load_za_synonym_dict,
)

APP_DATA_DICT = Path(__file__).resolve().parents[1] / "app" / "data" / "za_synonyms.json"


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_synonym_cache()
    yield
    clear_synonym_cache()


class TestLoaderInterface:
    def test_file_loader_satisfies_interface(self):
        assert issubclass(JsonFileSynonymDictLoader, SynonymDictLoader)

    def test_missing_file_raises_synonym_dict_error(self, tmp_path):
        loader = JsonFileSynonymDictLoader(tmp_path / "nope.json")
        with pytest.raises(SynonymDictError, match="not readable"):
            loader.load()

    def test_invalid_json_raises_synonym_dict_error(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(SynonymDictError, match="not valid JSON"):
            JsonFileSynonymDictLoader(bad).load()

    def test_missing_version_raises(self, tmp_path):
        d = tmp_path / "d.json"
        d.write_text(json.dumps({"jurisdiction": "za", "synonyms": {}}), encoding="utf-8")
        with pytest.raises(SynonymDictError, match="version"):
            JsonFileSynonymDictLoader(d).load()

    def test_missing_jurisdiction_raises(self, tmp_path):
        d = tmp_path / "d.json"
        d.write_text(json.dumps({"version": "1.0", "synonyms": {}}), encoding="utf-8")
        with pytest.raises(SynonymDictError, match="jurisdiction"):
            JsonFileSynonymDictLoader(d).load()

    def test_aliases_must_be_string_lists(self, tmp_path):
        d = tmp_path / "d.json"
        d.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "jurisdiction": "za",
                    "synonyms": {"employment": {"dismissal": "firing"}},
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(SynonymDictError, match="list of strings"):
            JsonFileSynonymDictLoader(d).load()

    def test_minimal_valid_dict_roundtrip(self, tmp_path):
        d = tmp_path / "d.json"
        d.write_text(
            json.dumps(
                {
                    "version": "9.9",
                    "jurisdiction": "za",
                    "synonyms": {"t": {"Term": ["alias one", "alias two"]}},
                }
            ),
            encoding="utf-8",
        )
        sd = JsonFileSynonymDictLoader(d).load()
        assert sd.version == "9.9"
        assert sd.expand_term("term", domain="t") == ["alias one", "alias two"]


class TestZaDictV1:
    @pytest.fixture(scope="class")
    def za(self):
        return JsonFileSynonymDictLoader(APP_DATA_DICT).load()

    def test_metadata(self, za):
        assert za.jurisdiction == "za"
        assert za.version == "1.0"

    # -- BCEA --------------------------------------------------------------

    def test_bcea_act_alias(self, za):
        assert za.lookup_act("bcea") == "Basic Conditions of Employment Act 75 of 1997"
        assert za.lookup_act("BCEA") == za.lookup_act("bcea")  # case-insensitive

    def test_bcea_synonym_expansion(self, za):
        aliases = za.expand_term("bcea")
        assert "basic conditions of employment act" in [a.lower() for a in aliases]
        assert "act 75 of 1997" in aliases

    def test_bcea_overtime_section_patterns(self, za):
        assert "section 10" in za.sections_for("overtime")
        assert "s 10" in za.sections_for("overtime")

    # -- LRA ---------------------------------------------------------------

    def test_lra_act_alias(self, za):
        assert za.lookup_act("lra") == "Labour Relations Act 66 of 1995"

    def test_lra_unfair_dismissal_expansion(self, za):
        aliases = {a.lower() for a in za.expand_term("unfair_dismissal")}
        assert "unfair dismissal" in aliases
        assert "wrongful dismissal" in aliases
        assert "automatically unfair dismissal" in aliases

    def test_lra_dismissal_colloquialisms(self, za):
        aliases = {a.lower() for a in za.expand_term("dismissal", domain="employment")}
        assert "firing" in aliases
        assert "sacking" in aliases
        assert "retrenchment" in aliases

    def test_lra_section_188_patterns(self, za):
        patterns = za.sections_for("unfair_dismissal")
        assert "section 185" in patterns
        assert "section 187" in patterns

    # -- POPIA -------------------------------------------------------------

    def test_popia_act_alias(self, za):
        assert za.lookup_act("popia") == "Protection of Personal Information Act 4 of 2013"

    def test_popia_synonym_expansion(self, za):
        aliases = {a.lower() for a in za.expand_term("popia")}
        assert "protection of personal information act" in aliases
        assert "act 4 of 2013" in aliases
        assert "data protection" in aliases

    def test_popia_processing_sections(self, za):
        patterns = za.sections_for("popia_processing")
        assert "section 11" in patterns
        assert "section 12" in patterns

    # -- generic behaviour --------------------------------------------------

    def test_expand_term_excludes_the_term_itself(self, za):
        assert "dismissal" not in za.expand_term("dismissal", domain="employment")

    def test_expand_term_unknown_is_empty(self, za):
        assert za.expand_term("nonexistent-term-xyz") == []

    def test_cross_domain_expansion_dedupes(self, za):
        # "contract" exists in employment and contract_law domains.
        aliases = za.expand_term("contract")
        lowered = [a.lower() for a in aliases]
        assert len(lowered) == len(set(lowered))

    def test_cached_loader_matches_direct_load(self):
        direct = JsonFileSynonymDictLoader(APP_DATA_DICT).load()
        cached = load_za_synonym_dict()
        assert cached.term_count == direct.term_count
        assert cached.act_aliases == direct.act_aliases
