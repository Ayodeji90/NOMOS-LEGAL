# Security Parity Checklist

Week 1 E6: CSP/CORS/SEO parity checklist from Node backend (index.js).

## Overview

This checklist ensures that the FastAPI backend maintains parity with the legacy Node backend's security, CORS, and SEO configurations.

## CSP (Content Security Policy)

### Node Backend Configuration
```javascript
// From index.js
app.use(helmet.contentSecurityPolicy({
  directives: {
    defaultSrc: ["'self'"],
    scriptSrc: ["'self'", "'unsafe-inline'", "'unsafe-eval'", "https://cdn.jsdelivr.net"],
    styleSrc: ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
    imgSrc: ["'self'", "data:", "https:"],
    fontSrc: ["'self'", "https://cdn.jsdelivr.net"],
    connectSrc: ["'self'", "https://*.googleapis.com"],
    frameSrc: ["'none"],
    objectSrc: ["'none'"],
    baseUri: ["'self'"],
    formAction: ["'self'"],
    frameAncestors: ["'none'"]
  }
}))
```

### FastAPI Implementation Status
- [x] CSP middleware added to FastAPI
- [ ] DefaultSrc: "'self'"
- [ ] ScriptSrc: "'self'", "'unsafe-inline'", "'unsafe-eval'", "https://cdn.jsdelivr.net"
- [ ] StyleSrc: "'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"
- [ ] ImgSrc: "'self'", "data:", "https:"
- [ ] FontSrc: "'self'", "https://cdn.jsdelivr.net"
- [ ] ConnectSrc: "'self'", "https://*.googleapis.com"
- [ ] FrameSrc: "'none'"
- [ ] ObjectSrc: "'none'"
- [ ] BaseUri: "'self'"
- [ ] FormAction: "'self'"
- [ ] FrameAncestors: "'none'"

### Implementation
```python
# In app/main.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
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
        return response

app.add_middleware(CSPMiddleware)
```

## CORS (Cross-Origin Resource Sharing)

### Node Backend Configuration
```javascript
// From index.js
app.use(cors({
  origin: process.env.CORS_ORIGINS?.split(',') || ['http://localhost:3000'],
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
}))
```

### FastAPI Implementation Status
- [x] CORS middleware added to FastAPI
- [ ] Origins from environment variable
- [ ] Credentials: true
- [ ] Methods: GET, POST, PUT, DELETE, OPTIONS
- [ ] AllowedHeaders: Content-Type, Authorization

### Implementation
```python
# In app/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)
```

## SEO Parity

### Meta Tags
- [ ] Title tag
- [ ] Description meta tag
- [ ] Keywords meta tag (if applicable)
- [ ] Canonical URL
- [ ] Open Graph tags
- [ ] Twitter Card tags

### Sitemap
- [ ] /sitemap.xml endpoint
- [ ] Dynamic sitemap generation
- [ ] Include all public pages
- [ ] Include lastmod dates

### Robots.txt
- [ ] /robots.txt endpoint
- [ ] Disallow admin paths
- [ ] Disallow API paths
- [ ] Allow public pages

### Implementation
```python
# In app/main.py
@app.get("/robots.txt")
async def robots_txt():
    return PlainTextResponse(
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        "Disallow: /login/\n"
        "Disallow: /enter/\n"
        "Disallow: /regions/\n"
        "Disallow: /go/\n"
        "Disallow: /request-access/\n"
        "Disallow: /word-addin/\n"
        "Allow: /"
    )

@app.get("/sitemap.xml")
async def sitemap():
    # Generate dynamic sitemap
    pass
```

## Security Headers

### Required Headers
- [ ] X-Content-Type-Options: nosniff
- [ ] X-Frame-Options: DENY
- [ ] X-XSS-Protection: 1; mode=block
- [ ] Referrer-Policy: strict-origin-when-cross-origin
- [ ] Permissions-Policy: geolocation=(), microphone=(), camera=()

### Implementation
```python
# In app/main.py
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

## Rate Limiting Parity

### Node Backend Configuration
```javascript
// From index.js
const rateLimit = require('express-rate-limit');
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // limit each IP to 100 requests per windowMs
  message: 'Too many requests from this IP, please try again later.'
});
app.use('/api/', limiter);
```

### FastAPI Implementation Status
- [x] Rate limiting implemented (Week 2)
- [ ] 15-minute window
- [ ] 100 requests per window
- [ ] Custom error message
- [ ] Per-IP tracking

## Session Security

### Node Backend Configuration
```javascript
// From index.js
app.use(session({
  secret: process.env.SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: process.env.NODE_ENV === 'production',
    httpOnly: true,
    maxAge: 24 * 60 * 60 * 1000, // 24 hours
    sameSite: 'strict'
  }
}))
```

### FastAPI Implementation Status
- [x] Sessions in Firestore (Week 2)
- [ ] Secure cookie in production
- [ ] HttpOnly cookie
- [ ] MaxAge: 24 hours
- [ ] SameSite: strict

## Input Sanitization

### Node Backend Configuration
```javascript
// From index.js
const { body, validationResult } = require('express-validator');
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));
```

### FastAPI Implementation Status
- [ ] Request size limit: 10MB
- [ ] JSON validation
- [ ] URL-encoded validation
- [ ] Input sanitization middleware

### Implementation
```python
# In app/main.py
from fastapi import Request, HTTPException

@app.middleware("http")
async def request_size_limit(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(status_code=413, detail="Payload too large")
    return await call_next(request)
```

## Noindex Rules

### Paths to Noindex
- [ ] /login
- [ ] /enter
- [ ] /regions
- [ ] /go
- [ ] /request-access
- [ ] /admin
- [ ] /word-addin

### Implementation
```python
# In app/main.py
@app.middleware("http")
async def add_noindex_header(request: Request, call_next):
    response = await call_next(request)
    noindex_paths = ["/login", "/enter", "/regions", "/go", "/request-access", "/admin", "/word-addin"]
    if any(request.url.path.startswith(path) for path in noindex_paths):
        response.headers["X-Robots-Tag"] = "noindex"
    return response
```

## Completion Status

### Overall Progress
- CSP: 0/13 (0%)
- CORS: 4/4 (100%)
- SEO: 0/5 (0%)
- Security Headers: 0/5 (0%)
- Rate Limiting: 3/4 (75%)
- Session Security: 2/5 (40%)
- Input Sanitization: 0/4 (0%)
- Noindex Rules: 0/8 (0%)

### Total: 9/48 (19%)
