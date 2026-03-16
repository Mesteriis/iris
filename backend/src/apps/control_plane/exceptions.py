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


class TopologyDraftConcurrencyConflict(TopologyDraftStateError):
    def __init__(
        self,
        draft_id: int,
        *,
        expected_version: int | None,
        current_version: int | None,
    ) -> None:
        self.draft_id = int(draft_id)
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(f"Draft '{self.draft_id}' is stale and must be rebased on the latest published topology.")


__all__ = [
    "ControlPlaneError",
    "EventConsumerNotFound",
    "EventDefinitionNotFound",
    "EventRouteCompatibilityError",
    "EventRouteConflict",
    "EventRouteNotFound",
    "TopologyDraftConcurrencyConflict",
    "TopologyDraftNotFound",
    "TopologyDraftStateError",
]
