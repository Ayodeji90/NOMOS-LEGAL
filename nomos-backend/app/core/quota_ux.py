"""
Quota UX improvements for rate limit responses.

Week 3 E6: Quota UX (429 copy + headers).
This provides user-friendly error messages and informative headers when rate limits are hit.
"""
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse


class QuotaUX:
    """Manages quota-related user experience improvements."""

    @staticmethod
    def create_rate_limit_response(
        request: Request,
        limit: int,
        window: int,
        remaining: int,
        reset_time: int | None = None,
    ) -> JSONResponse:
        """
        Create a user-friendly 429 response with informative headers.

        Args:
            request: The incoming request
            limit: Rate limit (requests per window)
            window: Time window in seconds
            remaining: Remaining requests in window
            reset_time: Unix timestamp when window resets

        Returns:
            JSONResponse with 429 status and informative headers
        """
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time or 0),
            "X-RateLimit-Window": str(window),
            "Retry-After": str(window),
        }

        # User-friendly error message
        error_detail = (
            f"You have exceeded the rate limit of {limit} requests per {window} seconds. "
            f"Please wait before making another request. "
            f"You can try again in approximately {window} seconds."
        )

        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "detail": error_detail,
                "limit": limit,
                "window": window,
                "remaining": remaining,
                "reset_at": reset_time,
            },
            headers=headers,
        )

    @staticmethod
    def create_quota_exceeded_response(
        request: Request,
        quota_limit: int,
        period: str,
        reset_time: int | None = None,
    ) -> JSONResponse:
        """
        Create a user-friendly response when quota is exceeded.

        Args:
            request: The incoming request
            quota_limit: Quota limit (e.g., 1000 requests per day)
            period: Quota period (e.g., "day", "month")
            reset_time: Unix timestamp when quota resets

        Returns:
            JSONResponse with 429 status and informative headers
        """
        headers = {
            "X-Quota-Limit": str(quota_limit),
            "X-Quota-Period": period,
            "X-Quota-Reset": str(reset_time or 0),
            "Retry-After": str(86400),  # 24 hours default
        }

        error_detail = (
            f"You have exceeded your quota of {quota_limit} requests per {period}. "
            f"Please upgrade your plan or wait until your quota resets. "
            f"Contact support if you need a higher quota."
        )

        return JSONResponse(
            status_code=429,
            content={
                "error": "Quota exceeded",
                "detail": error_detail,
                "quota_limit": quota_limit,
                "period": period,
                "reset_at": reset_time,
            },
            headers=headers,
        )

    @staticmethod
    def add_quota_headers(
        response: Response,
        limit: int,
        remaining: int,
        window: int,
        reset_time: int | None = None,
    ) -> Response:
        """
        Add quota headers to an existing response.

        This can be used to add quota information to successful responses
        so clients can track their usage.
        """
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time or 0)
        response.headers["X-RateLimit-Window"] = str(window)
        return response


# Global instance
quota_ux = QuotaUX()


def get_quota_ux() -> QuotaUX:
    """Get the global quota UX instance."""
    return quota_ux
