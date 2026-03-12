from __future__ import annotations

import random
from datetime import datetime, timezone

from faker import Faker

SEED = 20260312

random.seed(SEED)
Faker.seed(SEED)
fake = Faker()
fake.seed_instance(SEED)


def json_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
