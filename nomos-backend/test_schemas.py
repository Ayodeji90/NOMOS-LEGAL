#!/usr/bin/env python3
"""
Test script to validate the JSON schemas created for Week 1 tasks.
This tests that the Pydantic models can be instantiated and serialized to JSON.
"""

import sys
import os
from pydantic import ValidationError

# Add the app directory to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_query_understanding_schema():
    """Test the query understanding schema."""
    print("Testing Query Understanding Schema...")

    from app.schemas.query_understanding import QueryUnderstandingInput, QueryUnderstandingOutput

    # Test input
    try:
        input_data = QueryUnderstandingInput(
            query="What are the overtime provisions in the Basic Conditions of Employment Act?",
            jurisdiction_hint="za",
            history=[{"role": "user", "content": "Previous question"}]
        )
        print("✓ QueryUnderstandingInput validation passed")
        print(f"  Input JSON: {input_data.json()}")
    except ValidationError as e:
        print(f"✗ QueryUnderstandingInput validation failed: {e}")
        return False

    # Test output
    try:
        output_data = QueryUnderstandingOutput(
            jurisdiction="za",
            question_type="interpretation",
            expanded_queries=[
                "What are the overtime provisions in the Basic Conditions of Employment Act?",
                "Overtime rules BCEA",
                "Basic Conditions of Employment Act overtime"
            ],
            named_acts=["Basic Conditions of Employment Act"],
            intent_category="statutory_interpretation",
            confidence=0.85,
            multi_jurisdiction=False,
            complexity_score=0.4
        )
        print("✓ QueryUnderstandingOutput validation passed")
        print(f"  Output JSON: {output_data.json()}")
    except ValidationError as e:
        print(f"✗ QueryUnderstandingOutput validation failed: {e}")
        return False

    return True

def test_writer_schema():
    """Test the writer schema."""
    print("\nTesting Writer Schema...")

    from app.schemas.writer import WriterInput, WriterOutput

    # Test input
    try:
        input_data = WriterInput(
            query="What are the overtime provisions in the Basic Conditions of Employment Act?",
            jurisdiction="za",
            excerpts=[
                {
                    "n": 1,
                    "citation": "Basic Conditions of Employment Act section 6(1)",
                    "excerpt": "An employer may not require or permit an employee to work overtime except under an agreement to work overtime.",
                    "sourceText": "An employer may not require or permit an employee to work overtime except under an agreement to work overtime.",
                    "act": "Basic Conditions of Employment Act",
                    "section": "6(1)"
                }
            ],
            history=[],
            is_repair=False
        )
        print("✓ WriterInput validation passed")
        print(f"  Input JSON: {input_data.json()}")
    except ValidationError as e:
        print(f"✗ WriterInput validation failed: {e}")
        return False

    # Test output
    try:
        output_data = WriterOutput(
            insufficientContext=False,
            directAnswer="An employer may not require or permit an employee to work overtime except under an agreement to work overtime. [1]",
            explanation="The Basic Conditions of Employment Act section 6(1) clearly states that overtime work requires an agreement between employer and employee.",
            gaps="The excerpt does not specify limits on overtime hours or rates of pay for overtime work.",
            followUps=["What are the maximum overtime hours allowed per week?", "What is the overtime pay rate required by law?"],
            metadata={"model": "gemini-pro", "tokens_used": 150}
        )
        print("✓ WriterOutput validation passed")
        print(f"  Output JSON: {output_data.json()}")
    except ValidationError as e:
        print(f"✗ WriterOutput validation failed: {e}")
        return False

    return True

def test_verifier_schema():
    """Test the verifier schema."""
    print("\nTesting Verifier Schema...")

    from app.schemas.verifier import VerifierInput, VerifierVerdict

    # Test input
    try:
        input_data = VerifierInput(
            query="What are the overtime provisions in the Basic Conditions of Employment Act?",
            answer="An employer may not require or permit an employee to work overtime except under an agreement to work overtime. [1]",
            excerpts=[
                {
                    "n": 1,
                    "citation": "Basic Conditions of Employment Act section 6(1)",
                    "excerpt": "An employer may not require or permit an employee to work overtime except under an agreement to work overtime.",
                    "sourceText": "An employer may not require or permit an employee to work overtime except under an agreement to work overtime.",
                    "act": "Basic Conditions of Employment Act",
                    "section": "6(1)"
                }
            ],
            jurisdiction="za",
            is_repair=False
        )
        print("✓ VerifierInput validation passed")
        print(f"  Input JSON: {input_data.json()}")
    except ValidationError as e:
        print(f"✗ VerifierInput validation failed: {e}")
        return False

    # Test output - valid case
    try:
        output_data = VerifierVerdict(
            grounded=True,
            citation_issues=[],
            section_issues=[],
            entailment_issues=[],
            currency_issues=[],
            confidence=0.95,
            suggested_repairs=[],
            should_repair=False,
            summary="The answer is well-grounded in the retrieved excerpt with proper citation."
        )
        print("✓ VerifierVerdict validation passed (valid case)")
        print(f"  Output JSON: {output_data.json()}")
    except ValidationError as e:
        print(f"✗ VerifierVerdict validation failed: {e}")
        return False

    # Test output - invalid case
    try:
        output_data = VerifierVerdict(
            grounded=False,
            citation_issues=["Citation [2] refers to non-existent excerpt 2"],
            section_issues=[],
            entailment_issues=["The answer claims overtime is prohibited, but the excerpt only requires agreement"],
            currency_issues=[],
            confidence=0.7,
            suggested_repairs=["Check that citation [1] correctly references the source excerpt"],
            should_repair=True,
            summary="The answer has citation issues that need to be resolved."
        )
        print("✓ VerifierVerdict validation passed (invalid case)")
        print(f"  Output JSON: {output_data.json()}")
    except ValidationError as e:
        print(f"✗ VerifierVerdict validation failed: {e}")
        return False

    return True

def main():
    """Run all schema tests."""
    print("=" * 60)
    print("NOMOS AI Week 1 Schema Validation Tests")
    print("=" * 60)

    success = True
    success &= test_query_understanding_schema()
    success &= test_writer_schema()
    success &= test_verifier_schema()

    print("\n" + "=" * 60)
    if success:
        print("✓ ALL TESTS PASSED - Schemas are working correctly!")
        print("✓ Ready to proceed with Week 1 deliverables")
    else:
        print("✗ SOME TESTS FAILED - Please fix the issues above")
    print("=" * 60)

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())