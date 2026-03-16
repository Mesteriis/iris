from datetime import UTC, datetime, timezone

from polyfactory.factories.dataclass_factory import DataclassFactory
from polyfactory.fields import Use
from src.apps.patterns.domain.base import PatternDetection

from tests.factories.base import fake


class PatternDetectionFactory(DataclassFactory[PatternDetection]):
    __check_model__ = False

    slug = Use(lambda: fake.random_element(elements=("bull_flag", "head_shoulders", "bollinger_squeeze")))
    signal_type = Use(lambda: f"pattern_{fake.random_element(elements=('bull_flag', 'head_shoulders', 'bollinger_squeeze'))}")
    confidence = Use(lambda: round(fake.pyfloat(min_value=0.35, max_value=0.95, positive=True), 2))
    candle_timestamp = Use(lambda: datetime.now(UTC))
    category = Use(lambda: fake.random_element(elements=("continuation", "structural", "volatility")))
    attributes = Use(dict)
