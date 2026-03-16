"""Compatibility entrypoint for the HA bridge runtime surface."""

from iris.apps.integrations.ha.application.bridge_runtime import (
    HABridgeFacade,
    HACommandDispatch,
    ProjectionClock,
    ProjectionVersion,
    RuntimeSnapshot,
)

__all__ = [
    "HABridgeFacade",
    "HACommandDispatch",
    "ProjectionClock",
    "ProjectionVersion",
    "RuntimeSnapshot",
]
