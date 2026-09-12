"""
Access gate for NOMOS backend.

Week 1 E6: Access gate (allowlist/waitlist) for controlling user access.
This provides a centralized access control mechanism for the application.
"""
import logging

import structlog
from typing import Any

from app.core.config import settings

logger = structlog.get_logger(__name__)


class AccessGate:
    """Access control gate for user authentication and authorization."""

    def __init__(self):
        self.logger = logger.bind(service="AccessGate")
        self.allowlist = set(getattr(settings, "ACCESS_ALLOWLIST", []))
        self.waitlist_enabled = getattr(settings, "WAITLIST_ENABLED", False)
        self.logger.info(
            "Access gate initialized",
            allowlist_size=len(self.allowlist),
            waitlist_enabled=self.waitlist_enabled,
        )

    def is_email_allowed(self, email: str) -> bool:
        """
        Check if email is allowed to access the application.

        If allowlist is configured, only emails on the allowlist are allowed.
        If waitlist is enabled, new users are placed on waitlist.
        """
        email_lower = email.lower().strip()

        # Check allowlist first
        if self.allowlist:
            if email_lower in self.allowlist:
                self.logger.debug("Email allowed via allowlist", email=email_lower)
                return True
            else:
                self.logger.warning("Email not on allowlist", email=email_lower)
                return False

        # If no allowlist, allow all (unless waitlist is enabled)
        if self.waitlist_enabled:
            # In production, this would check a waitlist database
            # For now, we'll allow all for prototype
            self.logger.debug("Waitlist enabled, allowing email", email=email_lower)
            return True

        self.logger.debug("Email allowed (no restrictions)", email=email_lower)
        return True

    def is_api_key_allowed(self, api_key_hash: str) -> bool:
        """
        Check if API key is allowed to access the application.

        In production, this would check against a database of active API keys.
        For now, we'll allow all for prototype.
        """
        # In production, check database for active API keys
        self.logger.debug("API key allowed (prototype mode)")
        return True

    def check_access(
        self,
        email: str | None = None,
        api_key_hash: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Check if access is granted based on email or API key.

        Returns:
            Tuple of (allowed, reason)
        """
        if api_key_hash:
            if self.is_api_key_allowed(api_key_hash):
                return True, None
            else:
                return False, "API key not authorized"

        if email:
            if self.is_email_allowed(email):
                return True, None
            else:
                return False, "Email not on allowlist"

        return False, "No valid credentials provided"

    def add_to_allowlist(self, email: str):
        """Add email to allowlist (for admin use)."""
        email_lower = email.lower().strip()
        self.allowlist.add(email_lower)
        self.logger.info("Email added to allowlist", email=email_lower)

    def remove_from_allowlist(self, email: str):
        """Remove email from allowlist (for admin use)."""
        email_lower = email.lower().strip()
        self.allowlist.discard(email_lower)
        self.logger.info("Email removed from allowlist", email=email_lower)

    def get_allowlist(self) -> list[str]:
        """Get current allowlist (for admin use)."""
        return sorted(self.allowlist)


# Global instance
access_gate = AccessGate()


def get_access_gate() -> AccessGate:
    """Get the global access gate instance."""
    return access_gate
