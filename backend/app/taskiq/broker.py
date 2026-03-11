from taskiq_redis import RedisStreamBroker

from app.core.config import get_settings

settings = get_settings()

broker = RedisStreamBroker(
    url=settings.redis_url,
    queue_name="iris:taskiq",
    consumer_group_name="iris:backend",
)
