"""Structural override rules for controlling provision checks.

Week 10: Demote controlling-provision to suggestion + structural-override rules file.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StructuralOverrideRules:
    """Manager for structural override rules."""

    def __init__(self, rules_path: str | None = None):
        """Initialize rules manager.

        Args:
            rules_path: Path to rules JSON file. If None, uses default.
        """
        if rules_path is None:
            rules_path = "app/data/structural_override_rules.json"

        self._rules_path = Path(rules_path)
        self._rules: dict[str, Any] = {}
        self._load_rules()

    def _load_rules(self) -> None:
        """Load rules from JSON file."""
        try:
            with open(self._rules_path) as f:
                self._rules = json.load(f)
            logger.info(f"Loaded structural override rules from {self._rules_path}")
        except FileNotFoundError:
            logger.warning(f"Rules file not found at {self._rules_path}, using defaults")
            self._rules = {"jurisdictions": {}, "global_defaults": {}}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding rules file: {e}")
            self._rules = {"jurisdictions": {}, "global_defaults": {}}

    def should_demote_to_suggestion(self, jurisdiction: str) -> bool:
        """Check if controlling provision should be demoted to suggestion."""
        jur_rules = self._rules.get("jurisdictions", {}).get(jurisdiction, {})
        if "demote_to_suggestion" in jur_rules:
            return jur_rules["demote_to_suggestion"]

        # Fall back to global default
        global_defaults = self._rules.get("global_defaults", {})
        return global_defaults.get("demote_to_suggestion", True)

    def get_override_action(
        self,
        jurisdiction: str,
        section_text: str,
        citation: str,
    ) -> str | None:
        """
        Get override action for a section based on structural rules.

        Args:
            jurisdiction: Jurisdiction code
            section_text: Text of the section
            citation: Citation of the section

        Returns:
            Action: 'suggest' (demote to suggestion), 'block' (hard block), or None (no override)
        """
        jur_rules = self._rules.get("jurisdictions", {}).get(jurisdiction, {})
        overrides = jur_rules.get("overrides", [])

        # If no jurisdiction-specific overrides, use global
        if not overrides:
            overrides = self._rules.get("global_defaults", {}).get("overrides", [])

        # Check each override pattern
        for override in overrides:
            pattern = override.get("pattern", "")
            action = override.get("action", "")

            # Check pattern in section text or citation
            if pattern and pattern.lower() in section_text.lower():
                logger.info(f"Override matched: pattern='{pattern}', action={action}")
                return action

            if pattern and pattern.lower() in citation.lower():
                logger.info(f"Override matched in citation: pattern='{pattern}', action={action}")
                return action

        return None

    def get_override_reason(
        self,
        jurisdiction: str,
        section_text: str,
        citation: str,
    ) -> str | None:
        """Get reason for override."""
        jur_rules = self._rules.get("jurisdictions", {}).get(jurisdiction, {})
        overrides = jur_rules.get("overrides", [])

        if not overrides:
            overrides = self._rules.get("global_defaults", {}).get("overrides", [])

        for override in overrides:
            pattern = override.get("pattern", "")
            reason = override.get("reason", "")

            if pattern and pattern.lower() in section_text.lower():
                return reason

            if pattern and pattern.lower() in citation.lower():
                return reason

        return None


# Global instance for dependency injection
structural_rules = StructuralOverrideRules()
