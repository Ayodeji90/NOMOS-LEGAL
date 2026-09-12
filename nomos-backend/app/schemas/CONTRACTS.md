# NOMOS AI JSON Contracts

This document defines the JSON contracts for the AI pipeline components:
- Query Understanding
- Writer
- Verifier

These contracts ensure consistent communication between services.

## Query Understanding Contract

### Input (QueryUnderstandingInput)
```json
{
  "query": "string (1-2500 chars)",
  "jurisdiction_hint": "string|null (optional, e.g. 'za')",
  "history": "array of objects (max 6 items)"
}
```

### Output (QueryUnderstandingOutput)
```json
{
  "jurisdiction": "string (e.g. 'za', 'gb', 'us')",
  "question_type": "one of: definition, interpretation, procedure, comparison, compliance, history, other",
  "expanded_queries": "array of strings (max 5 items)",
  "named_acts": "array of strings",
  "intent_category": "one of: statutory_interpretation, case_law_precedent, procedural_question, definition_request, compliance_check, historical_inquiry, other",
  "confidence": "number (0.0 to 1.0)",
  "multi_jurisdiction": "boolean",
  "complexity_score": "number (0.0 to 1.0)"
}
```

## Writer Contract

### Input (WriterInput)
```json
{
  "query": "string (1-2500 chars)",
  "jurisdiction": "string (e.g. 'za')",
  "excerpts": "array of objects (min 1 item)",
  "understanding": "QueryUnderstandingOutput|null (optional)",
  "history": "array of objects (max 6 items)",
  "is_repair": "boolean",
  "verification_failures": "array of strings|null (optional)"
}
```

### Output (WriterOutput)
```json
{
  "insufficientContext": "boolean",
  "directAnswer": "string (max 2000 chars)",
  "explanation": "string",
  "gaps": "string",
  "followUps": "array of strings (max 3 items)",
  "metadata": "object|null (optional)"
}
```

## Verifier Contract

### Input (VerifierInput)
```json
{
  "query": "string (1-2500 chars)",
  "answer": "string (min 1 char)",
  "excerpts": "array of objects (min 1 item)",
  "jurisdiction": "string (e.g. 'za')",
  "is_repair": "boolean",
  "previous_failures": "array of strings|null (optional)"
}
```

### Output (VerifierVerdict)
```json
{
  "grounded": "boolean",
  "citation_issues": "array of strings",
  "section_issues": "array of strings",
  "entailment_issues": "array of strings",
  "currency_issues": "array of strings",
  "confidence": "number (0.0 to 1.0)",
  "suggested_repairs": "array of strings (max 3 items)",
  "should_repair": "boolean",
  "summary": "string"
}
```

## Response Contracts (from API)

### SearchResponse
```json
{
  "query": "string",
  "note": "string",
  "top": "array of objects",
  "errors": "array of objects",
  "missReason": "string|null",
  "sources": "array of SourceResponse objects",
  "structured": "StructuredAnswer object",
  "answer": "string",
  "grounded": "boolean",
  "provider": "string",
  "suggestedJurisdiction": "object|null",
  "writer": "object|null"
}
```

### RefusalResponse
(Same as SearchResponse but with missReason always present and indicating why refused)

### SourceResponse
```json
{
  "title": "string",
  "url": "string|null",
  "portion": "string|null",
  "excerpt": "string",
  "legal_citation": "string|null",
  "section": "string|null",
  "year": "string|null",
  "jurisdiction": "string|null"
}
```

### StructuredAnswer
```json
{
  "directAnswer": "string",
  "legalBasis": "array of objects",
  "explanation": "string",
  "gaps": "string",
  "grounded": "boolean"
}
```

## Notes

1. All string fields have reasonable length limits as defined in the Pydantic schemas
2. Arrays have maximum sizes to prevent excessive resource consumption
3. The contracts are designed to be forward-compatible - new fields can be added as optional
4. In Week 1, the query understanding returns stub data; actual Gemini Flash integration comes later
5. The writer and verifier will initially work with mock data until retrieval pipeline is built
6. The ASK_SYSTEM and ZA_ASK_ADDENDUM constants from the original JavaScript implementation have been preserved verbatim in the AI services for consistency

## ASK_SYSTEM and ZA_ASK_ADDENDUM (Verbatim from Original Implementation)

```javascript
const ASK_SYSTEM =
  "You are NOMOS, a legal research assistant. Ground only on the numbered excerpts retrieved for this request from the live Nomos corpus (Laws.Africa knowledge bases for South Africa; the Cloud Run legislation corpora for UK, US, Canada, Australia, Ireland, Germany, and New Zealand). Never use Discovery Engine. Never cite gs://juris-legal-documents/ paths. " +
  "Write like a careful lawyer talking to a colleague: clear prose, not a template. " +
  "Use ONLY the numbered excerpts. Do not invent Acts, sections, cases, tests, dates, or duties. " +
  "Every legal proposition must be followed by an [n] cite that matches an excerpt number. " +
  "Do not write 'the retrieved sources point primarily to'. Name the rule, then cite. " +
  "Before writing: identify the single most on-point retrieved section (the controlling provision) and lead with it in directAnswer, then explanation, then leave remaining limits in gaps. " +
  "If retrieved excerpts span more than one Act and the question names one Act or topic, ignore excerpts from other Acts. Do not blend jurisdictions. " +
  "Answer the current question only. Conversation is for follow-up pronouns, not for importing statutes from earlier turns unless those statutes appear in the excerpts. " +
  "If at least one excerpt is on-point, you MUST answer from it. Do not set insufficientContext=true because other excerpts are off-topic, truncated, or because court judgments are absent. Put those limits in gaps. " +
  "Set insufficientContext=true only when every excerpt is empty or none of them address the question at all. " +
  "gaps is required: name what the excerpts do not cover (other instruments, missing sections, case law). " +
  "Return JSON: {\"insufficientContext\": boolean, \"directAnswer\": string (3-8 short paragraphs, blank line between them, [n] cites; empty if insufficientContext), \"explanation\": string, \"gaps\": string, \"followUps\": string[3]}.";

const ZA_ASK_ADDENDUM =
  " For South African questions: if numbered statute excerpts address the question, answer from those excerpts and do not set insufficientContext merely because court judgments or common-law cases are absent. State in gaps that judgments and common-law case principles are not in this legislation corpus (judgments off pending licence). Do not imply there is no legal basis when statute was retrieved.";
```