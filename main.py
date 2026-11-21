import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import router
from app.config import get_settings
from app.database import get_engine
from app.middleware import BodyLimitMiddleware
from app.realtime import ConnectionHub
from app.realtime import router as websocket_router
from app.security import WindowLimiter


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app):
        settings.validate_required()
        app.state.hub = ConnectionHub()
        app.state.http_limiter = WindowLimiter(settings.HTTP_REQUESTS_PER_MINUTE, buckets=settings.HTTP_MAX_BUCKETS)
        app.state.ingest_limiter = WindowLimiter(1, settings.INGEST_MIN_INTERVAL_SECONDS, buckets=100)
        if not settings.TESTING:
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1"))
        yield
        for socket in list(app.state.hub.connections):
            try:
                await socket.close(code=1001)
            except Exception:
                pass
        if not settings.TESTING:
            await get_engine().dispose()

    app = FastAPI(title="MicroTransit API — Portfolio Edition", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key", "Content-Type"],
    )
    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        # Proxy headers are not trusted by this code. Configure trusted proxy IPs at the server.
        if not request.app.state.http_limiter.allow("http:" + ip):
            return JSONResponse({"detail": "Request rate exceeded"}, 429, headers={"Retry-After": "60"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request, exception):
        # Pydantic's default input field could echo a submitted credential.
        return JSONResponse(
            {"detail": [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exception.errors()]}, 422
        )

    @app.exception_handler(Exception)
    async def internal_error(_request, exception):
        logging.getLogger(__name__).error("Request failed (%s)", type(exception).__name__)
        return JSONResponse({"detail": "Request failed; check status before retrying"}, 500)

    @app.get("/health")
    async def health():
        return {"status": "ok", "edition": "synthetic portfolio"}

    app.include_router(router)
    app.include_router(websocket_router)
    return app


app = create_app()
