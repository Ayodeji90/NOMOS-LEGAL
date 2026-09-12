#!/usr/bin/env python3
"""
Test script for jurisdiction-specific thresholds (Week 7).
Demonstrates threshold loading and access for ZA and NG jurisdictions.
"""

import logging
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent))

from app.services.ai.thresholds import JurisdictionThresholds, thresholds

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_threshold_loading():
    """Test that thresholds file loads correctly."""
    logger.info("=" * 70)
    logger.info("Test 1: Threshold Loading")
    logger.info("=" * 70)
    
    # Check available jurisdictions
    available = thresholds.get_available_jurisdictions()
    logger.info(f"Available jurisdictions: {available}")
    
    assert "za" in available, "ZA should be available"
    assert "ng" in available, "NG should be available"
    
    logger.info("✅ PASS: Thresholds loaded correctly")


def test_za_thresholds():
    """Test South Africa thresholds."""
    logger.info("=" * 70)
    logger.info("Test 2: South Africa Thresholds")
    logger.info("=" * 70)
    
    jurisdiction = "za"
    
    # Test general thresholds
    coverage = thresholds.get_coverage_threshold(jurisdiction)
    logger.info(f"Coverage threshold: {coverage}")
    assert coverage == 0.35, f"Expected 0.35, got {coverage}"
    
    min_excerpts = thresholds.get_min_excerpts(jurisdiction)
    logger.info(f"Min excerpts: {min_excerpts}")
    assert min_excerpts == 3, f"Expected 3, got {min_excerpts}"
    
    citation_threshold = thresholds.get_citation_realism_threshold(jurisdiction)
    logger.info(f"Citation realism threshold: {citation_threshold}")
    assert citation_threshold == 0.8, f"Expected 0.8, got {citation_threshold}"
    
    section_threshold = thresholds.get_section_realism_threshold(jurisdiction)
    logger.info(f"Section realism threshold: {section_threshold}")
    assert section_threshold == 0.7, f"Expected 0.7, got {section_threshold}"
    
    entailment_threshold = thresholds.get_entailment_threshold(jurisdiction)
    logger.info(f"Entailment threshold: {entailment_threshold}")
    assert entailment_threshold == 0.6, f"Expected 0.6, got {entailment_threshold}"
    
    currency_days = thresholds.get_currency_disclosure_days(jurisdiction)
    logger.info(f"Currency disclosure days: {currency_days}")
    assert currency_days == 365, f"Expected 365, got {currency_days}"
    
    # Test Act-specific thresholds
    bcea_min = thresholds.get_act_min_excerpts(jurisdiction, "BCEA")
    logger.info(f"BCEA min excerpts: {bcea_min}")
    assert bcea_min == 2, f"Expected 2, got {bcea_min}"
    
    bcea_priority = thresholds.get_act_priority(jurisdiction, "BCEA")
    logger.info(f"BCEA priority: {bcea_priority}")
    assert bcea_priority == "high", f"Expected 'high', got {bcea_priority}"
    
    companies_min = thresholds.get_act_min_excerpts(jurisdiction, "Companies Act")
    logger.info(f"Companies Act min excerpts: {companies_min}")
    assert companies_min == 2, f"Expected 2, got {companies_min}"
    
    # Test jurisdiction name
    jur_name = thresholds.get_jurisdiction_name(jurisdiction)
    logger.info(f"Jurisdiction name: {jur_name}")
    assert jur_name == "South Africa", f"Expected 'South Africa', got {jur_name}"
    
    logger.info("✅ PASS: ZA thresholds correct")


def test_ng_thresholds():
    """Test Nigeria thresholds."""
    logger.info("=" * 70)
    logger.info("Test 3: Nigeria Thresholds")
    logger.info("=" * 70)
    
    jurisdiction = "ng"
    
    # Test general thresholds
    coverage = thresholds.get_coverage_threshold(jurisdiction)
    logger.info(f"Coverage threshold: {coverage}")
    assert coverage == 0.30, f"Expected 0.30, got {coverage}"
    
    min_excerpts = thresholds.get_min_excerpts(jurisdiction)
    logger.info(f"Min excerpts: {min_excerpts}")
    assert min_excerpts == 3, f"Expected 3, got {min_excerpts}"
    
    citation_threshold = thresholds.get_citation_realism_threshold(jurisdiction)
    logger.info(f"Citation realism threshold: {citation_threshold}")
    assert citation_threshold == 0.75, f"Expected 0.75, got {citation_threshold}"
    
    section_threshold = thresholds.get_section_realism_threshold(jurisdiction)
    logger.info(f"Section realism threshold: {section_threshold}")
    assert section_threshold == 0.65, f"Expected 0.65, got {section_threshold}"
    
    entailment_threshold = thresholds.get_entailment_threshold(jurisdiction)
    logger.info(f"Entailment threshold: {entailment_threshold}")
    assert entailment_threshold == 0.55, f"Expected 0.55, got {entailment_threshold}"
    
    currency_days = thresholds.get_currency_disclosure_days(jurisdiction)
    logger.info(f"Currency disclosure days: {currency_days}")
    assert currency_days == 365, f"Expected 365, got {currency_days}"
    
    # Test Act-specific thresholds
    labour_min = thresholds.get_act_min_excerpts(jurisdiction, "Labour Act")
    logger.info(f"Labour Act min excerpts: {labour_min}")
    assert labour_min == 2, f"Expected 2, got {labour_min}"
    
    labour_priority = thresholds.get_act_priority(jurisdiction, "Labour Act")
    logger.info(f"Labour Act priority: {labour_priority}")
    assert labour_priority == "high", f"Expected 'high', got {labour_priority}"
    
    cama_min = thresholds.get_act_min_excerpts(jurisdiction, "Companies and Allied Matters Act")
    logger.info(f"CAMA min excerpts: {cama_min}")
    assert cama_min == 2, f"Expected 2, got {cama_min}"
    
    # Test jurisdiction name
    jur_name = thresholds.get_jurisdiction_name(jurisdiction)
    logger.info(f"Jurisdiction name: {jur_name}")
    assert jur_name == "Nigeria", f"Expected 'Nigeria', got {jur_name}"
    
    logger.info("✅ PASS: NG thresholds correct")


def test_unknown_jurisdiction():
    """Test fallback to global defaults for unknown jurisdiction."""
    logger.info("=" * 70)
    logger.info("Test 4: Unknown Jurisdiction Fallback")
    logger.info("=" * 70)
    
    jurisdiction = "xx"  # Unknown jurisdiction
    
    # Should fall back to global defaults
    coverage = thresholds.get_coverage_threshold(jurisdiction)
    logger.info(f"Coverage threshold (fallback): {coverage}")
    assert coverage == 0.35, f"Expected global default 0.35, got {coverage}"
    
    min_excerpts = thresholds.get_min_excerpts(jurisdiction)
    logger.info(f"Min excerpts (fallback): {min_excerpts}")
    assert min_excerpts == 3, f"Expected global default 3, got {min_excerpts}"
    
    logger.info("✅ PASS: Fallback to global defaults works")


def test_case_insensitive_act_lookup():
    """Test case-insensitive Act name lookup."""
    logger.info("=" * 70)
    logger.info("Test 5: Case-Insensitive Act Lookup")
    logger.info("=" * 70)
    
    jurisdiction = "za"
    
    # Test different case variations of the defined keys
    bcea_min1 = thresholds.get_act_min_excerpts(jurisdiction, "BCEA")
    bcea_min2 = thresholds.get_act_min_excerpts(jurisdiction, "bcea")
    bcea_min3 = thresholds.get_act_min_excerpts(jurisdiction, "Bcea")
    
    logger.info(f"BCEA (uppercase): {bcea_min1}")
    logger.info(f"bcea (lowercase): {bcea_min2}")
    logger.info(f"Bcea (mixed case): {bcea_min3}")
    
    assert bcea_min1 == bcea_min2 == bcea_min3 == 2, "Case-insensitive lookup should work for defined keys"
    
    # Test Companies Act
    companies_min1 = thresholds.get_act_min_excerpts(jurisdiction, "Companies Act")
    companies_min2 = thresholds.get_act_min_excerpts(jurisdiction, "companies act")
    
    logger.info(f"Companies Act (title case): {companies_min1}")
    logger.info(f"companies act (lowercase): {companies_min2}")
    
    assert companies_min1 == companies_min2 == 2, "Case-insensitive lookup should work for multi-word keys"
    
    logger.info("✅ PASS: Case-insensitive Act lookup works")


def test_jurisdiction_exists():
    """Test jurisdiction existence check."""
    logger.info("=" * 70)
    logger.info("Test 6: Jurisdiction Existence Check")
    logger.info("=" * 70)
    
    assert thresholds.jurisdiction_exists("za") == True, "ZA should exist"
    assert thresholds.jurisdiction_exists("ng") == True, "NG should exist"
    assert thresholds.jurisdiction_exists("xx") == False, "XX should not exist"
    
    logger.info("✅ PASS: Jurisdiction existence check works")


def main():
    """Run all threshold tests."""
    logger.info("NOMOS v2 - Jurisdiction Thresholds Test")
    logger.info("Week 7 Deliverable: Extend thresholds to new jurisdictions (Nigeria)")
    logger.info("")
    
    try:
        test_threshold_loading()
        test_za_thresholds()
        test_ng_thresholds()
        test_unknown_jurisdiction()
        test_case_insensitive_act_lookup()
        test_jurisdiction_exists()
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("TEST SUMMARY")
        logger.info("=" * 70)
        logger.info("📋 DELIVERABLE STATUS:")
        logger.info("   ✅ JurisdictionThresholds implemented")
        logger.info("   ✅ Thresholds file created (jurisdiction_thresholds.json)")
        logger.info("   ✅ ZA thresholds defined")
        logger.info("   ✅ NG thresholds defined (Nigeria)")
        logger.info("   ✅ Global defaults defined")
        logger.info("   ✅ Act-specific thresholds defined")
        logger.info("")
        logger.info("📝 FEATURES:")
        logger.info("   - Coverage threshold per jurisdiction")
        logger.info("   - Minimum excerpts per jurisdiction")
        logger.info("   - Citation realism threshold per jurisdiction")
        logger.info("   - Section realism threshold per jurisdiction")
        logger.info("   - Entailment threshold per jurisdiction")
        logger.info("   - Currency disclosure threshold per jurisdiction")
        logger.info("   - Act-specific thresholds (min excerpts, priority)")
        logger.info("   - Fallback to global defaults")
        logger.info("   - Case-insensitive Act lookup")
        logger.info("")
        logger.info("🚀 READY FOR:")
        logger.info("   1. Integration with verifier service")
        logger.info("   2. Integration with retrieval service")
        logger.info("   3. Extension to additional jurisdictions")
        
    except AssertionError as e:
        logger.error(f"❌ TEST FAILED: {e}")
        raise


if __name__ == "__main__":
    main()
