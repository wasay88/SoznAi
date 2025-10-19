from __future__ import annotations

from unittest.mock import patch

from backend import main as entrypoint


def test_main_run_uses_env_port(monkeypatch):
    monkeypatch.setenv("PORT", "5001")
    with patch("uvicorn.run") as run_mock:
        entrypoint.run()
    run_mock.assert_called_once()
    args, kwargs = run_mock.call_args
    assert kwargs.get("port") == 5001
    assert kwargs.get("host") == "0.0.0.0"
