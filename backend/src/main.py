import uvicorn

from src.core.bootstrap import create_app
from src.core.settings import get_settings

settings = get_settings()
app = create_app()


def run() -> None:
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
    )


if __name__ == "__main__":
    run()
