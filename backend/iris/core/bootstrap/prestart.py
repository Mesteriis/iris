import asyncio
import logging

from iris.core.bootstrap.app import run_migrations
from iris.core.db.session import wait_for_database
from iris.runtime.orchestration.locks import wait_for_redis

LOGGER = logging.getLogger(__name__)


async def wait_for_runtime_dependencies() -> None:
    LOGGER.info("Waiting for database connectivity.")
    await wait_for_database()
    LOGGER.info("Waiting for Redis connectivity.")
    await wait_for_redis()


def run_prestart() -> None:
    asyncio.run(wait_for_runtime_dependencies())
    LOGGER.info("Applying database migrations.")
    run_migrations()
    LOGGER.info("Prestart checks completed.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_prestart()


if __name__ == "__main__":
    main()
