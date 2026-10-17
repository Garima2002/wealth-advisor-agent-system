"""FastAPI application entry point with correlation tracking, structured error handling, and security middlewares."""

import time
import uuid
from typing import Callable
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.logging_config import correlation_id_ctx, get_logger, setup_logging
from app.models.api import ErrorResponse

logger = get_logger("api.gateway")


def create_app() -> FastAPI:
    """Application factory for the Wealth Advisor Multi-Agent API."""
    setup_logging(log_level=settings.LOG_LEVEL)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Autonomous multi-agent system for wealth management: ingests client financial data, "
            "fetches CRM context, identifies financial anomalies through explainable rules, and produces "
            "actionable advisory insights with human-in-the-loop review."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 1. Correlation ID & Observability Middleware
    @app.middleware("http")
    async def correlation_and_logging_middleware(request: Request, call_next: Callable) -> Response:
        corr_id = request.headers.get("X-Correlation-ID") or f"req_{uuid.uuid4().hex[:10]}"
        correlation_id_ctx.set(corr_id)

        start_time = time.perf_counter()
        logger.info(
            f"Incoming {request.method} {request.url.path}",
            extra={"stage": "api_request", "correlation_id": corr_id}
        )

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Correlation-ID"] = corr_id
            logger.info(
                f"Completed {request.method} {request.url.path} with status {response.status_code} in {duration_ms}ms",
                extra={
                    "stage": "api_response",
                    "duration_ms": duration_ms,
                    "correlation_id": corr_id,
                }
            )
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                f"Unhandled exception on {request.method} {request.url.path}: {exc}",
                extra={
                    "stage": "api_error",
                    "duration_ms": duration_ms,
                    "error_category": type(exc).__name__,
                    "correlation_id": corr_id,
                },
                exc_info=True
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error_code="INTERNAL_SERVER_ERROR",
                    message="An unexpected server error occurred while processing the request.",
                    details={"error_type": type(exc).__name__}
                ).model_dump(),
                headers={"X-Correlation-ID": corr_id}
            )

    # 2. Schema Validation Error Handler
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        corr_id = correlation_id_ctx.get() or "unknown"
        logger.warning(
            f"Validation error on {request.url.path}: {exc.errors()}",
            extra={"stage": "validation_failure", "correlation_id": corr_id}
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT if hasattr(status, "HTTP_422_UNPROCESSABLE_CONTENT") else 422,
            content=ErrorResponse(
                error_code="VALIDATION_ERROR",
                message="Submitted request payload failed schema validation.",
                details={"errors": exc.errors()}
            ).model_dump(),
            headers={"X-Correlation-ID": corr_id}
        )

    # Include API Routers
    app.include_router(router)

    return app


app = create_app()
