from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..metrics import REQUEST_COUNT, REQUEST_ERRORS, REQUEST_LATENCY


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log requests with structured JSON and feed Prometheus metrics."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._logger = logging.getLogger("soznai.request")
        if self._logger.level == logging.NOTSET:
            self._logger.setLevel(logging.INFO)
        self._logger.propagate = True

    async def dispatch(  # type: ignore[override]
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        request_id = str(uuid4())
        request.state.request_id = request_id

        path_template = _resolve_path_template(request)

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            _observe_metrics(request.method, path_template, 500, duration_ms)
            self._logger.error(
                "request error",
                extra={
                    "request_id": request_id,
                    "path": path_template,
                    "method": request.method,
                    "status": 500,
                    "duration_ms": round(duration_ms, 3),
                    "user": getattr(request.state, "telemetry_user", None),
                },
                exc_info=True,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        status = response.status_code
        _observe_metrics(request.method, path_template, status, duration_ms)
        self._logger.info(
            "request complete",
            extra={
                "request_id": request_id,
                "path": path_template,
                "method": request.method,
                "status": status,
                "duration_ms": round(duration_ms, 3),
                "user": getattr(request.state, "telemetry_user", None),
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response


def _resolve_path_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return str(route.path)
    return request.url.path


def _observe_metrics(method: str, path: str, status: int, duration_ms: float) -> None:
    status_str = str(status)
    REQUEST_COUNT.labels(method=method, path=path, status=status_str).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration_ms / 1000)
    if status >= 500:
        REQUEST_ERRORS.labels(method=method, path=path, status=status_str).inc()
