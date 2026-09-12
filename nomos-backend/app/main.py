import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from structlog import get_logger

from app.core.access_gate import access_gate
from app.core.auth import auth_manager
from app.core.config import settings
from app.core.firestore import firestore_manager
from app.core.rate_limit import get_quota_manager, get_rate_limiter
from app.core.redis import redis_manager
from app.core.security_middleware import (
    CSPMiddleware,
    NoIndexMiddleware,
    SecurityHeadersMiddleware,
    get_robots_txt,
    get_sitemap_xml,
)
from app.core.shadow_traffic import get_shadow_traffic_middleware
from app.db.init import init_database
from app.db.session import db_manager

logging.basicConfig(level=settings.LOG_LEVEL)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "Starting application", version=settings.APP_VERSION, environment=settings.ENVIRONMENT
    )

    use_fakeredis = not settings.use_real_redis
    use_firestore_emulator = not settings.use_real_firestore

    redis_manager.initialize(use_fakeredis=use_fakeredis)
    firestore_manager.initialize(use_emulator=use_firestore_emulator)
    await init_database()

    get_rate_limiter()
    get_quota_manager()

    logger.info("Application startup complete")
    yield

    logger.info("Shutting down application")
    await redis_manager.close()
    await firestore_manager.close()
    await db_manager.close()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="NOMOS v2 - Legal AI/RAG Backend",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Add shadow traffic middleware in production (Week 3 E1)
if settings.ENVIRONMENT == "production" and settings.SHADOW_TRAFFIC_STAGING_URL:
    shadow_middleware = get_shadow_traffic_middleware()
    app.middleware("http")(shadow_middleware)

# Add security middleware (Week 7 E6)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSPMiddleware)
app.add_middleware(NoIndexMiddleware)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    if not settings.ENABLE_REQUEST_LOGGING:
        return await call_next(request)

    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    xff = request.headers.get("X-Forwarded-For", "")

    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        client_ip=client_ip,
        xff=xff,
    )

    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time_ms=round(process_time * 1000, 2),
        )
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            "request_failed",
            method=request.method,
            path=request.url.path,
            error=str(e),
            process_time_ms=round(process_time * 1000, 2),
        )
        raise


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    db_healthy = await db_manager.health_check()
    redis_healthy = await redis_manager.health_check()

    return {
        "status": "healthy" if db_healthy and redis_healthy else "degraded",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "checks": {
            "database": "ok" if db_healthy else "failed",
            "redis": "ok" if redis_healthy else "failed",
        },
    }


@app.get("/ready", tags=["Health"])
async def readiness_check() -> JSONResponse:
    db_healthy = await db_manager.health_check()
    redis_healthy = await redis_manager.health_check()

    ready = db_healthy and redis_healthy
    status_code = 200 if ready else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "ready": ready,
            "checks": {
                "database": "ok" if db_healthy else "failed",
                "redis": "ok" if redis_healthy else "failed",
            },
        },
    )


@app.get("/live", tags=["Health"])
async def liveness_check() -> PlainTextResponse:
    return PlainTextResponse("ok")


@app.get(f"{settings.API_PREFIX}/health", tags=["Health"])
async def api_health_check() -> dict:
    return await health_check()


@app.get("/robots.txt", tags=["SEO"])
async def robots_txt():
    """Robots.txt endpoint for SEO (Week 7 E6)."""
    return get_robots_txt()


@app.get("/sitemap.xml", tags=["SEO"])
async def sitemap_xml():
    """Sitemap.xml endpoint for SEO (Week 7 E6)."""
    return get_sitemap_xml()


from app.api.v1 import admin, auth, canary, draft, improve, review, search

app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(search.router, prefix=settings.API_PREFIX)
app.include_router(draft.router, prefix=settings.API_PREFIX)
app.include_router(review.router, prefix=settings.API_PREFIX)
app.include_router(improve.router, prefix=settings.API_PREFIX)
app.include_router(admin.router, prefix=f"{settings.API_PREFIX}/admin/access", tags=["Admin"])
app.include_router(canary.router, prefix=f"{settings.API_PREFIX}/admin/canary", tags=["Admin"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        reload=settings.is_development,
    )
