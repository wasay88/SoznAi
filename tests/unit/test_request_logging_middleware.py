from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from backend.app.core.logging import configure_logging
from backend.app.metrics import REQUEST_COUNT, REQUEST_ERRORS
from backend.app.middleware import RequestLoggingMiddleware


def _metric_value(counter, **labels) -> float:
    for family in counter.collect():
        for sample in family.samples:
            if all(sample.labels.get(key) == value for key, value in labels.items()):
                return sample.value
    return 0.0


def _app_with_middleware() -> FastAPI:
    configure_logging()
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    return app


def test_request_logging_success_adds_header() -> None:
    app = _app_with_middleware()

    @app.get("/ping")
    async def ping() -> dict[str, str]:  # pragma: no cover - executed via client
        return {"pong": "ok"}

    before = _metric_value(REQUEST_COUNT, method="GET", path="/ping", status="200")
    with TestClient(app) as client:
        response = client.get("/ping")
    after = _metric_value(REQUEST_COUNT, method="GET", path="/ping", status="200")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")
    assert after == pytest.approx(before + 1.0)


def test_request_logging_failure_logs_error() -> None:
    app = _app_with_middleware()

    @app.get("/boom")
    async def boom() -> dict[str, str]:  # pragma: no cover - executed via client
        raise RuntimeError("boom")

    before_count = _metric_value(REQUEST_COUNT, method="GET", path="/boom", status="500")
    before_errors = _metric_value(REQUEST_ERRORS, method="GET", path="/boom", status="500")

    with TestClient(app) as client:
        with pytest.raises(RuntimeError):
            client.get("/boom")

    after_count = _metric_value(REQUEST_COUNT, method="GET", path="/boom", status="500")
    after_errors = _metric_value(REQUEST_ERRORS, method="GET", path="/boom", status="500")

    assert after_count == pytest.approx(before_count + 1.0)
    assert after_errors == pytest.approx(before_errors + 1.0)
