from dataclasses import dataclass

from iris.apps.control_plane.read_models import TopologyDraftReadModel


@dataclass(slots=True, frozen=True)
class TopologyDraftLifecycleResult:
    draft: TopologyDraftReadModel
    published_version_number: int | None = None


__all__ = ["TopologyDraftLifecycleResult"]
