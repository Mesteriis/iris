"""Compatibility entrypoint for pattern task service foundations."""

from iris.apps.patterns.task_runtime_base import PatternTaskBase, read_cached_regime_async

__all__ = ["PatternTaskBase", "read_cached_regime_async"]
