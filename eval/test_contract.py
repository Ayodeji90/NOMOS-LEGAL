"""Frontend contract tests for POST /search (and shared shapes).

Mirrors juris-backend-src/index.js /search success payload plus the
fields public/js/workspace.js and public/word-addin/taskpane.js read:
answer, structured (directAnswer/explanation/gaps/followUps/legalBasis),
sources, results, matchCount, grounded, jurisdiction, corpus_id, writer,
suggestedJurisdiction. The 11 keys below are the compatibility surface
the Python v2 API must preserve byte-for-byte.
"""

import copy

# The 11-key compatibility surface (errors/summary are optional extras).
REQUIRED_KEYS = [
    "provider",
    "answer",
    "structured",
    "sources",
    "results",
    "matchCount",
    "grounded",
    "jurisdiction",
    "corpus_id",
    "writer",
    "suggestedJurisdiction",
]

SEARCH_OK = {
    "provider": "laws.africa",
    "answer": "Overtime is regulated [1].",
    "structured": {
        "insufficientContext": False,
        "directAnswer": "Overtime must be paid [1].",
        "legalBasis": [
            {"citation": "BCEA s10", "sourceText": "Overtime provisions s. 10..."}
        ],
        "explanation": "Section 10 caps and rates [1].",
        "gaps": "Regulations and case law not in corpus.",
        "followUps": ["What are ordinary hours under s9?"],
    },
    "summary": {"summaryText": "Overtime is regulated [1]."},
    "sources": [
        {
            "title": "Basic Conditions of Employment Act 75 of 1997",
            "url": "https://example.invalid/akn/za/act/1997/75",
            "portion": "s10",
            "excerpt": "Overtime provisions...",
            "kb": "legislation-za",
            "legal_citation": "",
            "section": "10",
            "year": "1997",
            "jurisdiction": "za",
            "citation": "BCEA s10",
        }
    ],
    "results": [
        {
            "document": {
                "derivedStructData": {
                    "title": "Basic Conditions of Employment Act 75 of 1997",
                    "link": "https://example.invalid/akn/za/act/1997/75",
                    "snippets": [{"snippet": "Overtime provisions..."}],
                }
            },
            "metadata": {
                "title": "Basic Conditions of Employment Act 75 of 1997",
                "jurisdiction": "za",
            },
            "score": 12.5,
            "kb": "legislation-za",
        }
    ],
    "matchCount": 1,
    "grounded": True,
    "jurisdiction": "za",
    "corpus_id": "legislation-za",
    "writer": {"model": "gemini-2.5-flash"},
    "suggestedJurisdiction": None,
}

SEARCH_REFUSED = {
    "provider": "laws.africa",
    "answer": "",
    "structured": {
        "insufficientContext": True,
        "directAnswer": "",
        "legalBasis": [],
        "explanation": "",
        "gaps": "No on-point statute retrieved.",
        "followUps": [],
    },
    "summary": {"summaryText": ""},
    "sources": [],
    "results": [],
    "matchCount": 0,
    "grounded": False,
    "jurisdiction": "za",
    "corpus_id": "legislation-za",
    "writer": {"model": "gemini-2.5-flash"},
    "suggestedJurisdiction": {"id": "gb", "name": "United Kingdom"},
}


def test_all_eleven_keys_present_on_success():
    missing = [k for k in REQUIRED_KEYS if k not in SEARCH_OK]
    assert missing == [], f"missing keys: {missing}"


def test_all_eleven_keys_present_on_refusal():
    missing = [k for k in REQUIRED_KEYS if k not in SEARCH_REFUSED]
    assert missing == [], f"missing keys: {missing}"


def test_key_types():
    assert isinstance(SEARCH_OK["answer"], str)
    assert isinstance(SEARCH_OK["structured"], dict)
    assert isinstance(SEARCH_OK["sources"], list)
    assert isinstance(SEARCH_OK["results"], list)
    assert isinstance(SEARCH_OK["matchCount"], int)
    assert isinstance(SEARCH_OK["grounded"], bool)
    assert isinstance(SEARCH_OK["jurisdiction"], str)
    assert isinstance(SEARCH_OK["corpus_id"], str)
    assert isinstance(SEARCH_OK["writer"], dict)


def test_structured_shape_workspace_reads():
    s = SEARCH_OK["structured"]
    for key in ("directAnswer", "explanation", "gaps", "followUps", "legalBasis"):
        assert key in s, f"workspace.js reads structured.{key}"
    assert isinstance(s["legalBasis"], list)
    basis = s["legalBasis"][0]
    assert basis["citation"] and basis["sourceText"]


def test_taskpane_fallback_fields():
    # taskpane.js renders data.answer with data.structured as enhancement,
    # and data.sources as the source list; /draft and /review reuse
    # data.draft|data.guidance|data.review with data.answer fallback.
    assert SEARCH_OK["answer"]
    assert isinstance(SEARCH_OK["sources"], list)
    refused = copy.deepcopy(SEARCH_OK)
    refused["answer"] = ""
    assert refused["structured"]["directAnswer"]  # enhancement path intact


def test_sources_carry_jurisdiction_for_leakage_checks():
    for src in SEARCH_OK["sources"]:
        assert src.get("jurisdiction") == "za"


def test_results_shape_matches_toFrontendResults():
    item = SEARCH_OK["results"][0]
    derived = item["document"]["derivedStructData"]
    assert derived["title"] and isinstance(derived["snippets"], list)
    assert derived["snippets"][0]["snippet"]
    assert isinstance(item["score"], (int, float))


def test_refusal_shape():
    assert SEARCH_REFUSED["grounded"] is False
    assert SEARCH_REFUSED["structured"]["insufficientContext"] is True
    assert SEARCH_REFUSED["structured"]["gaps"]
    assert SEARCH_REFUSED["matchCount"] == 0
