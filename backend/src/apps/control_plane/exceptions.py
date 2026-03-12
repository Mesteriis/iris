from __future__ import annotations


class ControlPlaneError(Exception):
    pass


class EventDefinitionNotFound(ControlPlaneError):
    pass


class EventConsumerNotFound(ControlPlaneError):
    pass


class EventRouteNotFound(ControlPlaneError):
    pass


class EventRouteConflict(ControlPlaneError):
    pass


class EventRouteCompatibilityError(ControlPlaneError):
    pass


class TopologyDraftNotFound(ControlPlaneError):
    pass


class TopologyDraftStateError(ControlPlaneError):
    pass


__all__ = [
    "ControlPlaneError",
    "EventConsumerNotFound",
    "EventDefinitionNotFound",
    "EventRouteCompatibilityError",
    "EventRouteConflict",
    "EventRouteNotFound",
    "TopologyDraftNotFound",
    "TopologyDraftStateError",
]
