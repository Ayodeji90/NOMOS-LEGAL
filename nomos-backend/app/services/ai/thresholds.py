"""Jurisdiction-specific thresholds for verification and coverage checks.

This module loads and provides access to jurisdiction-specific thresholds
for verification, coverage checks, and other AI service parameters.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JurisdictionThresholds:
    """Manager for jurisdiction-specific thresholds."""

    def __init__(self, thresholds_path: str | None = None):
        """Initialize thresholds manager.

        Args:
            thresholds_path: Path to thresholds JSON file. If None, uses default.
        """
        if thresholds_path is None:
            # Default path relative to project root
            thresholds_path = "app/data/jurisdiction_thresholds.json"

        self._thresholds_path = Path(thresholds_path)
        self._thresholds: dict[str, Any] = {}
        self._load_thresholds()

    def _load_thresholds(self) -> None:
        """Load thresholds from JSON file."""
        try:
            with open(self._thresholds_path) as f:
                self._thresholds = json.load(f)
            logger.info(f"Loaded thresholds from {self._thresholds_path}")
            logger.info(
                f"Available jurisdictions: {list(self._thresholds.get('jurisdictions', {}).keys())}"
            )
        except FileNotFoundError:
            logger.warning(f"Thresholds file not found at {self._thresholds_path}, using defaults")
            self._thresholds = {"jurisdictions": {}, "global_defaults": {}}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding thresholds file: {e}")
            self._thresholds = {"jurisdictions": {}, "global_defaults": {}}

    def get_threshold(self, jurisdiction: str, key: str, default: Any = None) -> Any:
        """Get a threshold value for a specific jurisdiction.

        Args:
            jurisdiction: Jurisdiction code (e.g., 'za', 'ng')
            key: Threshold key (e.g., 'coverage_threshold')
            default: Default value if not found

        Returns:
            Threshold value or default
        """
        # Try jurisdiction-specific value
        jur_thresholds = self._thresholds.get("jurisdictions", {}).get(jurisdiction, {})
        if key in jur_thresholds:
            return jur_thresholds[key]

        # Fall back to global default
        global_defaults = self._thresholds.get("global_defaults", {})
        if key in global_defaults:
            return global_defaults[key]

        # Return provided default
        return default

    def get_coverage_threshold(self, jurisdiction: str) -> float:
        """Get coverage threshold for jurisdiction."""
        return self.get_threshold(jurisdiction, "coverage_threshold", default=0.35)

    def get_min_excerpts(self, jurisdiction: str) -> int:
        """Get minimum excerpts required for answer."""
        return self.get_threshold(jurisdiction, "min_excerpts_for_answer", default=3)

    def get_citation_realism_threshold(self, jurisdiction: str) -> float:
        """Get citation realism threshold."""
        return self.get_threshold(jurisdiction, "citation_realism_threshold", default=0.8)

    def get_section_realism_threshold(self, jurisdiction: str) -> float:
        """Get section realism threshold."""
        return self.get_threshold(jurisdiction, "section_realism_threshold", default=0.7)

    def get_entailment_threshold(self, jurisdiction: str) -> float:
        """Get entailment threshold."""
        return self.get_threshold(jurisdiction, "entailment_threshold", default=0.6)

    def get_currency_disclosure_days(self, jurisdiction: str) -> int:
        """Get currency disclosure threshold in days."""
        return self.get_threshold(jurisdiction, "currency_disclosure_days", default=365)

    def get_act_threshold(
        self, jurisdiction: str, act_name: str, key: str, default: Any = None
    ) -> Any:
        """Get Act-specific threshold.

        Args:
            jurisdiction: Jurisdiction code
            act_name: Name of the Act
            key: Threshold key (e.g., 'min_excerpts')
            default: Default value

        Returns:
            Act-specific threshold or default
        """
        jur_thresholds = self._thresholds.get("jurisdictions", {}).get(jurisdiction, {})
        acts = jur_thresholds.get("acts", {})

        # Try exact match first
        if act_name in acts:
            act_config = acts[act_name]
            if key in act_config:
                return act_config[key]

        # Try case-insensitive match
        act_lower = act_name.lower()
        for act_key, act_config in acts.items():
            if act_key.lower() == act_lower and key in act_config:
                return act_config[key]

        return default

    def get_act_min_excerpts(self, jurisdiction: str, act_name: str) -> int:
        """Get minimum excerpts required for a specific Act."""
        return self.get_act_threshold(jurisdiction, act_name, "min_excerpts", default=1)

    def get_act_priority(self, jurisdiction: str, act_name: str) -> str:
        """Get priority level for a specific Act."""
        return self.get_act_threshold(jurisdiction, act_name, "priority", default="medium")

    def get_jurisdiction_name(self, jurisdiction: str) -> str:
        """Get human-readable jurisdiction name."""
        jur_thresholds = self._thresholds.get("jurisdictions", {}).get(jurisdiction, {})
        return jur_thresholds.get("name", jurisdiction.upper())

    def get_available_jurisdictions(self) -> list[str]:
        """Get list of available jurisdictions."""
        return list(self._thresholds.get("jurisdictions", {}).keys())

    def jurisdiction_exists(self, jurisdiction: str) -> bool:
        """Check if jurisdiction has thresholds defined."""
        return jurisdiction in self._thresholds.get("jurisdictions", {})


# Global instance for dependency injection
thresholds = JurisdictionThresholds()
