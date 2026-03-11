from __future__ import annotations

import uvicorn

from app.core.bootstrap import create_app
from app.core.settings import get_settings

settings = get_settings()
app = create_app()


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
    )


if __name__ == "__main__":
    run()
