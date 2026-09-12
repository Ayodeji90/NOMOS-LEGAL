# NOMOS v2 - AI/LLM Engineer (E3) Week 7 Deliverable
## Extend Thresholds to New Jurisdictions (Nigeria)

**Role**: E3 — AI/LLM Engineer  
**Task**: Extend thresholds to new jurisdictions  
**Deliverable**: thresholds file covers 2 countries (ZA, NG)  
**Date**: 2026-09-11  
**Status**: ✅ COMPLETED

---

## ✅ Week 7 Deliverable - COMPLETED

### Task: Extend thresholds to new jurisdictions
**Status**: ✅ COMPLETED  
**Evidence**: `app/data/jurisdiction_thresholds.json`, `app/services/ai/thresholds.py`

### Implementation Details

**1. Jurisdiction Thresholds File**
- Created `app/data/jurisdiction_thresholds.json`
- Defined thresholds for South Africa (ZA)
- Defined thresholds for Nigeria (NG) - NEW
- Defined global defaults for fallback
- Structured for easy extension to additional jurisdictions

**2. JurisdictionThresholds Service**
- Created `app/services/ai/thresholds.py`
- Loads thresholds from JSON file
- Provides access methods for all threshold types
- Supports jurisdiction-specific and Act-specific thresholds
- Falls back to global defaults for unknown jurisdictions
- Case-insensitive Act name lookup

---

## 📊 Test Results

### Test Suite: `test_thresholds.py`

```
✅ JurisdictionThresholds implemented
✅ Thresholds file created (jurisdiction_thresholds.json)
✅ ZA thresholds defined
✅ NG thresholds defined (Nigeria)
✅ Global defaults defined
✅ Act-specific thresholds defined
```

### 6 Test Cases - ALL PASSED

**Test 1: Threshold Loading**
- ✅ Thresholds file loads correctly
- ✅ Available jurisdictions: ['za', 'ng']

**Test 2: South Africa Thresholds**
- ✅ Coverage threshold: 0.35
- ✅ Min excerpts: 3
- ✅ Citation realism threshold: 0.8
- ✅ Section realism threshold: 0.7
- ✅ Entailment threshold: 0.6
- ✅ Currency disclosure days: 365
- ✅ BCEA min excerpts: 2, priority: high
- ✅ Companies Act min excerpts: 2
- ✅ Jurisdiction name: South Africa

**Test 3: Nigeria Thresholds**
- ✅ Coverage threshold: 0.30
- ✅ Min excerpts: 3
- ✅ Citation realism threshold: 0.75
- ✅ Section realism threshold: 0.65
- ✅ Entailment threshold: 0.55
- ✅ Currency disclosure days: 365
- ✅ Labour Act min excerpts: 2, priority: high
- ✅ CAMA min excerpts: 2
- ✅ Jurisdiction name: Nigeria

**Test 4: Unknown Jurisdiction Fallback**
- ✅ Falls back to global defaults for unknown jurisdiction
- ✅ Coverage threshold (fallback): 0.35
- ✅ Min excerpts (fallback): 3

**Test 5: Case-Insensitive Act Lookup**
- ✅ BCEA (uppercase): 2
- ✅ bcea (lowercase): 2
- ✅ Bcea (mixed case): 2
- ✅ Companies Act (title case): 2
- ✅ companies act (lowercase): 2

**Test 6: Jurisdiction Existence Check**
- ✅ ZA exists
- ✅ NG exists
- ✅ Unknown jurisdiction does not exist

---

## 🔧 Technical Implementation

### File Structure
```
app/
├── data/
│   └── jurisdiction_thresholds.json    # Threshold definitions
└── services/ai/
    ├── thresholds.py                    # Threshold service
    └── __init__.py                      # Updated to export thresholds
```

### Threshold Structure

**General Thresholds per Jurisdiction:**
- `coverage_threshold` - Minimum coverage score for retrieval
- `min_excerpts_for_answer` - Minimum excerpts required to generate answer
- `citation_realism_threshold` - Threshold for citation realism check
- `section_realism_threshold` - Threshold for section realism check
- `entailment_threshold` - Threshold for NLI entailment check
- `currency_disclosure_days` - Days threshold for currency disclosure

**Act-Specific Thresholds:**
- `min_excerpts` - Minimum excerpts required for this Act
- `priority` - Priority level (high/medium/low)

### Key Methods

**JurisdictionThresholds.get_threshold()**
```python
def get_threshold(self, jurisdiction: str, key: str, default: Any = None) -> Any
```

**JurisdictionThresholds.get_coverage_threshold()**
```python
def get_coverage_threshold(self, jurisdiction: str) -> float
```

**JurisdictionThresholds.get_act_min_excerpts()**
```python
def get_act_min_excerpts(self, jurisdiction: str, act_name: str) -> int
```

---

## 📝 Threshold Values

### South Africa (ZA)
```json
{
  "coverage_threshold": 0.35,
  "min_excerpts_for_answer": 3,
  "citation_realism_threshold": 0.8,
  "section_realism_threshold": 0.7,
  "entailment_threshold": 0.6,
  "currency_disclosure_days": 365
}
```

**ZA Acts:**
- BCEA: min_excerpts=2, priority=high
- Companies Act: min_excerpts=2, priority=high
- Employment Equity Act: min_excerpts=1, priority=medium

### Nigeria (NG) - NEW
```json
{
  "coverage_threshold": 0.30,
  "min_excerpts_for_answer": 3,
  "citation_realism_threshold": 0.75,
  "section_realism_threshold": 0.65,
  "entailment_threshold": 0.55,
  "currency_disclosure_days": 365
}
```

**NG Acts:**
- Labour Act: min_excerpts=2, priority=high
- Companies and Allied Matters Act (CAMA): min_excerpts=2, priority=high
- Employee Compensation Act: min_excerpts=1, priority=medium

### Global Defaults
```json
{
  "coverage_threshold": 0.35,
  "min_excerpts_for_answer": 3,
  "citation_realism_threshold": 0.8,
  "section_realism_threshold": 0.7,
  "entailment_threshold": 0.6,
  "currency_disclosure_days": 365
}
```

---

## 🚀 Integration Steps

### Step 1: Use in Verifier Service
```python
from app.services.ai.thresholds import thresholds

# Get jurisdiction-specific threshold
citation_threshold = thresholds.get_citation_realism_threshold(jurisdiction)
section_threshold = thresholds.get_section_realism_threshold(jurisdiction)
```

### Step 2: Use in Retrieval Service
```python
from app.services.ai.thresholds import thresholds

# Get coverage threshold
coverage_threshold = thresholds.get_coverage_threshold(jurisdiction)
min_excerpts = thresholds.get_min_excerpts(jurisdiction)
```

### Step 3: Use in Gates
```python
from app.services.ai.thresholds import thresholds

# Get Act-specific threshold
act_min_excerpts = thresholds.get_act_min_excerpts(jurisdiction, act_name)
```

---

## ✅ Success Criteria

- [x] JurisdictionThresholds implemented
- [x] Thresholds file created (jurisdiction_thresholds.json)
- [x] ZA thresholds defined
- [x] NG thresholds defined (Nigeria)
- [x] Global defaults defined
- [x] Act-specific thresholds defined
- [x] Fallback to global defaults works
- [x] Case-insensitive Act lookup works
- [x] All tests pass

---

## 📊 Compliance with Implementation Plan

**Week 7 — Remaining countries CA, AU, IE, DE, NZ**

E3 — AI / LLM Engineer
- ✅ Task 1: Extend thresholds to new jurisdictions
- ✅ Deliverable: thresholds file covers 2 countries (ZA, NG)

**Note**: Per user request, only extended to Nigeria (NG) instead of CA, AU, IE, DE, NZ. The structure is ready for easy extension to additional jurisdictions when needed.

**Joint gate**: all 8 countries queryable in staging.
- ✅ Thresholds structure ready for 8 countries
- ✅ Currently configured for 2 countries (ZA, NG)
- ✅ Easy to add CA, AU, IE, DE, NZ when parsers are ready

---

## 🎯 Next Steps

1. **Integrate thresholds with verifier service** - Use jurisdiction-specific thresholds in verification checks
2. **Integrate thresholds with retrieval service** - Use coverage thresholds in retrieval
3. **Integrate thresholds with gates** - Use Act-specific thresholds in named-Act gate
4. **Add more jurisdictions** - Extend to CA, AU, IE, DE, NZ when parsers are ready
5. **Monitor threshold effectiveness** - Track pass/fail rates per jurisdiction

---

## ✅ Conclusion

Week 7 deliverable for AI/LLM Engineer (E3) has been **successfully completed**. The jurisdiction-specific thresholds are now:

1. **Implemented** with a clean JSON structure
2. **Extended** to Nigeria (NG) in addition to South Africa (ZA)
3. **Tested** with comprehensive test coverage (6 tests, all green)
4. **Ready** for integration with verifier, retrieval, and gates
5. **Extensible** for easy addition of CA, AU, IE, DE, NZ when needed

The system now has jurisdiction-specific thresholds for verification and coverage checks, enabling different quality standards per jurisdiction based on corpus size and legal system characteristics.
