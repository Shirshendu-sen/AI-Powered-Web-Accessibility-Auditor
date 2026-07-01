"""FastAPI application entry point (Phase 7).

Wires CORS from config, registers the scans router, installs a global
exception handler that returns structured JSON (never a stack trace),
and emits one log line per request with a request id + duration.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.routes import scans as scans_router

log = logging.getLogger("app.api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="Accessibility Auditor API", version="0.7.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001 — re-raised after logging
        duration_ms = int((time.perf_counter() - started) * 1000)
        log.exception(
            "request failed rid=%s method=%s path=%s duration_ms=%s",
            request_id, request.method, request.url.path, duration_ms,
        )
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "request rid=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["x-request-id"] = request_id
    return response


def _error_response(status_code: int, code: str, message: str,
                    detail: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    return _error_response(exc.status_code, code=str(exc.status_code),
                           message=str(exc.detail))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return _error_response(422, code="validation_error",
                           message="Request body failed validation.",
                           detail=exc.errors())


@app.exception_handler(Exception)
async def handle_uncaught(request: Request, exc: Exception):
    log.exception("uncaught exception on %s %s", request.method, request.url.path)
    return _error_response(500, code="internal_error",
                           message="An unexpected server error occurred.")


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "config": config.public_config_snapshot()}


app.include_router(scans_router.router, prefix="/api")
