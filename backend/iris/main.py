import uvicorn

from iris.core.bootstrap import create_app
from iris.core.settings import get_settings

settings = get_settings()
app = create_app()


def run() -> None:
    uvicorn.run(
        "iris.main:app",
        host=settings.api_host,
        port=settings.api_port,
    )


if __name__ == "__main__":
    run()
