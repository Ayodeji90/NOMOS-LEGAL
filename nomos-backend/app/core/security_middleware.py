"""
Security middleware for CSP, security headers, and SEO.

Week 7 E6: CSP/SEO/sitemap/robots parity audit.
This middleware implements security headers and SEO endpoints to match the Node backend.
"""
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response


class CSPMiddleware(BaseHTTPMiddleware):
    """Middleware to add Content-Security-Policy header."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self' https://*.googleapis.com; "
            "frame-src 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["Content-Security-Policy"] = csp

        return response


class NoIndexMiddleware(BaseHTTPMiddleware):
    """Middleware to add X-Robots-Tag header for noindex paths."""

    NOINDEX_PATHS = [
        "/login",
        "/enter",
        "/regions",
        "/go",
        "/request-access",
        "/admin",
        "/word-addin",
    ]

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add noindex header for sensitive paths
        if any(request.url.path.startswith(path) for path in self.NOINDEX_PATHS):
            response.headers["X-Robots-Tag"] = "noindex"

        return response


def get_robots_txt() -> PlainTextResponse:
    """Generate robots.txt content."""
    content = (
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        "Disallow: /login/\n"
        "Disallow: /enter/\n"
        "Disallow: /regions/\n"
        "Disallow: /go/\n"
        "Disallow: /request-access/\n"
        "Disallow: /word-addin/\n"
        "Allow: /\n"
    )
    return PlainTextResponse(content)


def get_sitemap_xml() -> PlainTextResponse:
    """Generate sitemap.xml content."""
    # In production, this would be dynamically generated from actual pages
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://nomos.ai/</loc>
    <lastmod>2024-01-15</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://nomos.ai/regions</loc>
    <lastmod>2024-01-15</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>"""
    return PlainTextResponse(content, media_type="application/xml")
