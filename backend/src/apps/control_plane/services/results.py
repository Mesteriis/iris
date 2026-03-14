from __future__ import annotations

from dataclasses import dataclass

from src.apps.control_plane.read_models import TopologyDraftReadModel


@dataclass(slots=True, frozen=True)
class TopologyDraftLifecycleResult:
    draft: TopologyDraftReadModel
    published_version_number: int | None = None


__all__ = ["TopologyDraftLifecycleResult"]
