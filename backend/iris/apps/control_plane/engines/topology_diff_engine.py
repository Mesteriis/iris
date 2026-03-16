from collections.abc import Iterable

from iris.apps.control_plane.engines.contracts import TopologyDiffPreviewItem
from iris.apps.control_plane.engines.route_engine import (
    command_from_payload,
    merge_route_command,
    route_snapshot_from_command,
    route_snapshot_from_read_model,
    route_to_snapshot,
)
from iris.apps.control_plane.enums import TopologyDraftChangeType
from iris.apps.control_plane.read_models import EventRouteReadModel, TopologyDraftChangeReadModel


def preview_topology_diff(
    *,
    live_routes: Iterable[EventRouteReadModel],
    changes: Iterable[TopologyDraftChangeReadModel],
) -> tuple[TopologyDiffPreviewItem, ...]:
    route_map = {route.route_key: route_to_snapshot(route_snapshot_from_read_model(route)) for route in live_routes}
    diff_items: list[TopologyDiffPreviewItem] = []

    for change in changes:
        payload = dict(change.payload_json or {})
        if change.change_type == TopologyDraftChangeType.ROUTE_CREATED:
            after = route_to_snapshot(route_snapshot_from_command(command_from_payload(payload)))
            route_map[after["route_key"]] = after
            diff_items.append(
                TopologyDiffPreviewItem(
                    change_type=change.change_type,
                    route_key=str(after["route_key"]),
                    before={},
                    after=after,
                )
            )
            continue

        if change.target_route_key is None:
            continue

        before = dict(route_map.get(change.target_route_key, {}))
        after = dict(before)
        route_key = change.target_route_key

        if change.change_type == TopologyDraftChangeType.ROUTE_DELETED:
            route_map.pop(change.target_route_key, None)
            diff_items.append(
                TopologyDiffPreviewItem(
                    change_type=change.change_type,
                    route_key=change.target_route_key,
                    before=before,
                    after={},
                )
            )
            continue

        if change.change_type == TopologyDraftChangeType.ROUTE_STATUS_CHANGED:
            after["status"] = str(payload["status"])
            if payload.get("notes") is not None:
                after["notes"] = str(payload["notes"])
        elif change.change_type == TopologyDraftChangeType.ROUTE_UPDATED:
            command = merge_route_command(before, payload)
            after = route_to_snapshot(route_snapshot_from_command(command))
            route_key = command.route_key

        if route_key != change.target_route_key:
            route_map.pop(change.target_route_key, None)
        route_map[route_key] = after
        diff_items.append(
            TopologyDiffPreviewItem(
                change_type=change.change_type,
                route_key=route_key,
                before=before,
                after=after,
            )
        )

    return tuple(diff_items)


__all__ = ["preview_topology_diff"]
