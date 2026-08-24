"""CronPanel application entry point.

Layering rules:
- routes/      -> HTTP transport only (no business logic)
- services/    -> business logic
- repositories -> database access
- core/        -> cross-cutting concerns (config, security, logging)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth as auth_routes
from app.api.routes import health as health_routes
from app.core.config import BASE_DIR, settings
from app.core.logging import get_logger, setup_logging
from app.database.init_db import create_tables

logger = get_logger("app.main")

FRONTEND_DIR = BASE_DIR.parent / "frontend"

_ERROR_INTERNAL = {
    "error": "INTERNAL_SERVER_ERROR",
    "message": "Ha ocurrido un error interno. Inténtelo de nuevo más tarde.",
}

_STATUS_ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    422: "VALIDATION_ERROR",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging(
        level=logging.DEBUG if settings.DEBUG else logging.INFO
    )
    create_tables()
    logger.info("%s v%s started.", settings.APP_NAME, settings.APP_VERSION)
    yield
    logger.info("%s stopped.", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# CORS: restricted to configured origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(status.HTTP_401_UNAUTHORIZED)
async def unauthorized_handler(_: Request, exc) -> JSONResponse:
    return _http_error_response(exc)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in error.get("loc", [])), "message": error.get("msg", "")}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Datos inválidos en la petición.",
            "details": details,
        },
    )


def _http_error_response(exc) -> JSONResponse:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        content = detail
    else:
        code = _STATUS_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
        content = {"error": code, "message": str(detail or "Error en la petición.")}
    headers = getattr(exc, "headers", None)
    return JSONResponse(status_code=exc.status_code, content=content, headers=headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full traceback goes to logs only; the client receives a safe message.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=_ERROR_INTERNAL)


app.include_router(health_routes.router)
app.include_router(auth_routes.router)

if FRONTEND_DIR.exists():
    # Static frontend served last so API routes take precedence.
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
