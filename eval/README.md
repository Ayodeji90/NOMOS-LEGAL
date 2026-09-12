# NOMOS eval harness (W1, E5 — Quality + Integration)

Scope: ZA-only prototype (Nigeria next). GB sets deferred to Phase 2.

## Layout

  eval/metrics.py          retrieval + faithfulness metric functions (stdlib only)
  eval/validate_golden.py  golden-file validator (run standalone or imported by tests)
  eval/golden_schema.json  JSON Schema documenting the golden-item contract
  eval/golden/za.json      30 golden QAs: 25 answerable + 5 must-refuse
  eval/test_metrics.py     unit tests for metrics (synthetic data)
  eval/test_golden.py      golden-set integrity tests (counts, traps, targets)
  eval/test_contract.py    /search 11-key contract vs workspace.js + taskpane.js

## Run

  python3 -m pytest eval/ -q
  python3 -m eval.validate_golden eval/golden/za.json

## CI gates (blocking)

  jurisdiction leakage rate == 0 (wrong-country excerpt = hard fail)
  refusal correctness == 100% (should-refuse but answered = hard fail)
  citation validity == 100% (every [n] resolves), invented-section rate == 0
  recall@10 / MRR / entailment: reported + tracked, bars set per jurisdiction
  from measured data once the hybrid path lands (W3-W4)

## Adding questions

  Append items to eval/golden/za.json following eval/golden_schema.json,
  then run the validator. Answerable items need >= 1 expected section in
  the form "<Act short> s<no>" (e.g. "BCEA s10"). Must-refuse items need
  a refusal_reason and empty expected_sections.
