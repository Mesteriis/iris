from taskiq_redis import RedisStreamBroker

from app.core.settings import get_settings

settings = get_settings()

GENERAL_TASKIQ_QUEUE_NAME = "iris:taskiq"
ANALYTICS_TASKIQ_QUEUE_NAME = "iris:taskiq:analytics"
GENERAL_TASKIQ_CONSUMER_GROUP = "iris:backend"
ANALYTICS_TASKIQ_CONSUMER_GROUP = "iris:backend:analytics"

broker = RedisStreamBroker(
    url=settings.redis_url,
    queue_name=GENERAL_TASKIQ_QUEUE_NAME,
    consumer_group_name=GENERAL_TASKIQ_CONSUMER_GROUP,
)

analytics_broker = RedisStreamBroker(
    url=settings.redis_url,
    queue_name=ANALYTICS_TASKIQ_QUEUE_NAME,
    consumer_group_name=ANALYTICS_TASKIQ_CONSUMER_GROUP,
)
