# SuggestedJurisdiction UX Contract

Week 5 E6: SuggestedJurisdiction UX contract frozen with frontend.

## Overview

When a user asks a question that is better answered by a different jurisdiction, the system should suggest the correct jurisdiction. This document defines the contract between backend and frontend for this feature.

## Backend Response Contract

### When Jurisdiction Mismatch is Detected

When the query understanding detects that the user's question is about a law in a different jurisdiction than the one selected, the backend should include a `suggestedJurisdiction` field in the response.

### Response Schema

```json
{
  "provider": "nomos",
  "answer": "...",
  "structured": {...},
  "sources": [...],
  "results": {...},
  "matchCount": 0,
  "grounded": true,
  "jurisdiction": "za",
  "corpus_id": "za-2024-01-15",
  "writer": "gemini-pro",
  "suggestedJurisdiction": {
    "code": "ng",
    "name": "Nigeria",
    "reason": "This question appears to be about Nigerian law. The Companies and Allied Matters Act 2020 is Nigerian legislation.",
    "confidence": 0.85
  },
  "errors": []
}
```

### SuggestedJurisdiction Schema

```typescript
interface SuggestedJurisdiction {
  code: string;           // Jurisdiction code (e.g., "ng", "za")
  name: string;           // Human-readable name (e.g., "Nigeria", "South Africa")
  reason: string;         // Explanation of why this jurisdiction is suggested
  confidence: number;     // Confidence score (0-1)
}
```

## Frontend Behavior

### Display Suggestion

When `suggestedJurisdiction` is present in the response:

1. **Show a prominent banner** at the top of the results
2. **Include the reason** for the suggestion
3. **Provide a button** to switch to the suggested jurisdiction
4. **Allow the user to dismiss** the suggestion

### Example UI

```
┌─────────────────────────────────────────────────────────────┐
│ ℹ️  This question appears to be about Nigerian law.          │
│    The Companies and Allied Matters Act 2020 is Nigerian      │
│    legislation.                                              │
│                                                              │
│    [Switch to Nigeria]  [Dismiss]                           │
└─────────────────────────────────────────────────────────────┘
```

### Switch Jurisdiction Action

When user clicks "Switch to Nigeria":

1. Update the jurisdiction selector to the suggested jurisdiction
2. Re-run the search with the new jurisdiction
3. Display the new results
4. Optionally, show a confirmation that the switch occurred

## Backend Implementation

### Detection Logic

Jurisdiction suggestions should be triggered when:

1. **Named Act Mismatch**: User asks about an Act that exists only in another jurisdiction
   - Example: "What does the Companies and Allied Matters Act say about..." (NG Act, but user selected ZA)

2. **Jurisdiction-Specific Terms**: Query contains terms specific to another jurisdiction
   - Example: "What are the provisions of the CAMA 2020?" (CAMA is Nigerian)

3. **Cross-Jurisdiction Traps**: Golden set includes cross-jurisdiction test cases
   - Example: "What is BCEA?" asked on GB picker should suggest ZA

### Confidence Thresholds

- **High confidence (≥0.8)**: Always suggest
- **Medium confidence (0.5-0.8)**: Suggest with lower prominence
- **Low confidence (<0.5)**: Do not suggest

### API Contract

The backend should include `suggestedJurisdiction` in the response when:

```python
# In the search endpoint response
if jurisdiction_mismatch_detected:
    response["suggestedJurisdiction"] = {
        "code": suggested_jurisdiction_code,
        "name": suggested_jurisdiction_name,
        "reason": explanation,
        "confidence": confidence_score,
    }
```

## Testing

### Test Cases

1. **Named Act Mismatch**
   - Query: "What does the CAMA 2020 say about..."
   - Selected Jurisdiction: ZA
   - Expected Suggestion: NG with high confidence

2. **Jurisdiction-Specific Terms**
   - Query: "Companies and Allied Matters Act provisions"
   - Selected Jurisdiction: ZA
   - Expected Suggestion: NG with high confidence

3. **No Mismatch**
   - Query: "What does the BCEA say about..."
   - Selected Jurisdiction: ZA
   - Expected: No suggestion

4. **Cross-Jurisdiction Trap**
   - Query: "What is BCEA?"
   - Selected Jurisdiction: GB
   - Expected Suggestion: ZA with high confidence

## Implementation Status

- [x] Backend response schema defined
- [ ] Backend detection logic implemented
- [ ] Frontend banner component created
- [ ] Frontend switch jurisdiction action implemented
- [ ] End-to-end testing completed
