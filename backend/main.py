from __future__ import annotations

import os

import uvicorn

from backend.app.main import app


def run() -> None:
    """Run the SoznAi FastAPI application with environment-aware port."""

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()

