from dataclasses import dataclass
from datetime import datetime

from polyfactory.factories.dataclass_factory import DataclassFactory
from polyfactory.fields import Use

from tests.factories.base import fake


@dataclass
class MetricSeed:
    regime: str
    activity_bucket: str
    activity_score: float
    analysis_priority: int
    price_current: float
    price_change_24h: float
    price_change_7d: float
    volume_change_24h: float
    volatility: float
    market_cap: float
    last_analysis_at: datetime
    trend: str = "up"
    trend_score: int = 8


class MetricSeedFactory(DataclassFactory[MetricSeed]):
    __check_model__ = False

    activity_score = Use(lambda: round(fake.pyfloat(min_value=40, max_value=99, positive=True), 2))
    analysis_priority = Use(lambda: fake.random_int(min=1, max=10))
    price_current = Use(lambda: round(fake.pyfloat(min_value=10, max_value=200000, positive=True), 2))
    price_change_24h = Use(lambda: round(fake.pyfloat(min_value=-15, max_value=15), 2))
    price_change_7d = Use(lambda: round(fake.pyfloat(min_value=-30, max_value=30), 2))
    volume_change_24h = Use(lambda: round(fake.pyfloat(min_value=-20, max_value=40), 2))
    volatility = Use(lambda: round(fake.pyfloat(min_value=0.01, max_value=0.15, positive=True), 3))
    market_cap = Use(lambda: round(fake.pyfloat(min_value=1_000_000, max_value=1_000_000_000_000, positive=True), 2))
    trend = Use(lambda: fake.random_element(elements=("up", "down", "flat")))
    trend_score = Use(lambda: fake.random_int(min=1, max=10))


@dataclass
class SignalSeed:
    signal_type: str
    confidence: float
    priority_score: float
    context_score: float
    regime_alignment: float
    candle_timestamp: datetime
    created_at: datetime


class SignalSeedFactory(DataclassFactory[SignalSeed]):
    __check_model__ = False

    confidence = Use(lambda: round(fake.pyfloat(min_value=0.5, max_value=0.99, positive=True), 2))
    priority_score = Use(lambda: round(fake.pyfloat(min_value=0.5, max_value=999, positive=True), 2))
    context_score = Use(lambda: round(fake.pyfloat(min_value=0.8, max_value=1.2, positive=True), 2))
    regime_alignment = Use(lambda: round(fake.pyfloat(min_value=0.8, max_value=1.2, positive=True), 2))


@dataclass
class DecisionSeed:
    decision: str
    confidence: float
    created_at: datetime


class DecisionSeedFactory(DataclassFactory[DecisionSeed]):
    __check_model__ = False

    confidence = Use(lambda: round(fake.pyfloat(min_value=0.5, max_value=0.99, positive=True), 3))


@dataclass
class StrategySeed:
    name: str
    description: str
    created_at: datetime


class StrategySeedFactory(DataclassFactory[StrategySeed]):
    __check_model__ = False

    name = Use(lambda: f"{fake.word().title()} {fake.word().title()}")
    description = Use(lambda: fake.sentence(nb_words=6))


@dataclass
class NarrativeSeed:
    reason: str
    created_at: datetime


class NarrativeSeedFactory(DataclassFactory[NarrativeSeed]):
    __check_model__ = False

    reason = Use(lambda: fake.sentence(nb_words=8))


@dataclass
class SectorSeed:
    name: str
    description: str


class SectorSeedFactory(DataclassFactory[SectorSeed]):
    __check_model__ = False

    name = Use(lambda: fake.random_element(elements=("store_of_value", "smart_contract", "high_beta", "payments")))
    description = Use(lambda: fake.sentence(nb_words=4))
