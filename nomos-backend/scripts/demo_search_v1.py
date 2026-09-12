#!/usr/bin/env python3
"""
Demo script v1 for Week 4 E5 deliverable.

Shows 5 answers + 2 refuses demonstrating the v2 API with:
- Hybrid retrieval (dense + lexical)
- Flash reranking
- Coverage gate
- Grounded answers with citations
- Refusal behavior for cross-jurisdiction and coverage gaps

Usage:
  python scripts/demo_search_v1.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.retrieval.service import retrieval_service
from app.services.ai.writer_service import writer_service
from app.services.ai.verifier_service import verifier_service
from app.services.ai.gates import gate_service


async def demo_query(query: str, jurisdiction: str = "za") -> dict:
    """Run a single query through the full pipeline."""
    print(f"\n{'='*70}")
    print(f"Query: {query}")
    print(f"Jurisdiction: {jurisdiction}")
    print(f"{'='*70}")

    # Step 1: Retrieval with coverage
    print("\n[1] Retrieval...")
    retrieval_result = await retrieval_service.retrieve_with_coverage(
        query=query,
        jurisdiction=jurisdiction,
        limit=50
    )
    
    print(f"  - Retrieved {len(retrieval_result.excerpts)} excerpts")
    print(f"  - Coverage: {retrieval_result.coverage:.2f}")
    print(f"  - Coverage OK: {retrieval_result.coverage_ok}")
    print(f"  - Degraded: {retrieval_result.degraded}")

    # Step 2: Check gates
    print("\n[2] Gates...")
    should_refuse, failure_reasons, suggested_jurisdiction = await gate_service.check_all_gates(
        query=query,
        jurisdiction=jurisdiction,
        excerpts=[{"sourceText": e.get("text", ""), "citation": e.get("citation", "")} for e in retrieval_result.excerpts]
    )
    
    if should_refuse:
        print(f"  - GATES BLOCKED: {', '.join(failure_reasons)}")
        if suggested_jurisdiction:
            print(f"  - Suggested jurisdiction: {suggested_jurisdiction}")
        return {
            "query": query,
            "jurisdiction": jurisdiction,
            "refused": True,
            "reason": ", ".join(failure_reasons),
            "suggested_jurisdiction": suggested_jurisdiction
        }
    
    print("  - Gates passed")

    # Step 3: Writer
    print("\n[3] Writer...")
    from app.schemas.writer import WriterInput
    writer_input = WriterInput(
        query=query,
        jurisdiction=jurisdiction,
        excerpts=[{"sourceText": e.get("text", ""), "citation": e.get("citation", "")} for e in retrieval_result.excerpts],
        history=[],
        is_repair=False
    )
    
    writer_output = await writer_service.write_answer(writer_input)
    print(f"  - Insufficient context: {writer_output.insufficientContext}")
    print(f"  - Direct answer length: {len(writer_output.directAnswer)} chars")
    print(f"  - Explanation length: {len(writer_output.explanation)} chars")

    # Step 4: Verifier
    print("\n[4] Verifier...")
    from app.schemas.verifier import VerifierInput
    verifier_input = VerifierInput(
        query=query,
        answer=writer_output.directAnswer + "\n" + writer_output.explanation,
        excerpts=[{"sourceText": e.get("text", ""), "citation": e.get("citation", "")} for e in retrieval_result.excerpts],
        jurisdiction=jurisdiction,
        is_repair=False
    )
    
    verifier_verdict = await verifier_service.verify(verifier_input)
    print(f"  - Grounded: {verifier_verdict.grounded}")
    print(f"  - Citation issues: {len(verifier_verdict.citation_issues)}")
    print(f"  - Section issues: {len(verifier_verdict.section_issues)}")
    print(f"  - Entailment issues: {len(verifier_verdict.entailment_issues)}")

    # Return result
    return {
        "query": query,
        "jurisdiction": jurisdiction,
        "refused": False,
        "coverage": retrieval_result.coverage,
        "coverage_ok": retrieval_result.coverage_ok,
        "n_excerpts": len(retrieval_result.excerpts),
        "direct_answer": writer_output.directAnswer,
        "explanation": writer_output.explanation,
        "gaps": writer_output.gaps,
        "grounded": verifier_verdict.grounded,
        "citation_issues": verifier_verdict.citation_issues,
        "section_issues": verifier_verdict.section_issues,
    }


async def main():
    """Run demo with 5 answers + 2 refuses."""
    print("="*70)
    print("NOMOS v2 Demo Script v1 - Week 4 E5 Deliverable")
    print("="*70)
    print("\nThis demo shows:")
    print("  - 5 successful answers with grounded citations")
    print("  - 2 refusals (cross-jurisdiction + coverage gap)")
    print()

    # Initialize database
    from app.db.session import db_manager
    if db_manager._engine is None:
        db_manager.initialize()

    # Demo queries
    demo_queries = [
        # 5 successful answers
        ("What are the overtime rules for employees under the BCEA?", "za"),
        ("What makes a dismissal unfair under LRA section 188?", "za"),
        ("On what lawful grounds may a business process personal information under POPIA?", "za"),
        ("What are the duties of directors under section 76 of the Companies Act 71 of 2008?", "za"),
        ("When is a consumer contract term unfair under sections 48 and 49 of the Consumer Protection Act?", "za"),
        # 2 refusals
        ("What are the unfair dismissal qualifying periods under the Employment Rights Act 1996?", "za"),  # Cross-jurisdiction trap
        ("What did the court hold on the merits in Mthembu v Santam Insurance?", "za"),  # Case-law gap
    ]

    results = []
    for query, jurisdiction in demo_queries:
        try:
            result = await demo_query(query, jurisdiction)
            results.append(result)
            
            # Print answer if not refused
            if not result.get("refused"):
                print(f"\n[ANSWER]")
                print(result.get("direct_answer", ""))
                if result.get("explanation"):
                    print(f"\n[EXPLANATION]")
                    print(result.get("explanation", ""))
                if result.get("gaps"):
                    print(f"\n[GAPS]")
                    print(result.get("gaps", ""))
            else:
                print(f"\n[REFUSED]")
                print(f"Reason: {result.get('reason', 'Unknown')}")
                if result.get("suggested_jurisdiction"):
                    print(f"Suggested jurisdiction: {result.get('suggested_jurisdiction')}")
            
        except Exception as e:
            print(f"\n[ERROR]")
            print(f"Failed: {e}")
            results.append({
                "query": query,
                "jurisdiction": jurisdiction,
                "refused": True,
                "error": str(e)
            })

    # Summary
    print("\n" + "="*70)
    print("DEMO SUMMARY")
    print("="*70)
    successful = sum(1 for r in results if not r.get("refused"))
    refused = sum(1 for r in results if r.get("refused"))
    grounded = sum(1 for r in results if r.get("grounded"))
    
    print(f"Total queries: {len(results)}")
    print(f"Successful answers: {successful}")
    print(f"Refusals: {refused}")
    print(f"Grounded answers: {grounded}")
    
    print("\n" + "="*70)
    print("Demo complete!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
