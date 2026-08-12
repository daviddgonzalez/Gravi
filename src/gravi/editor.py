"""In-session room editing.

Pure logic taking plain coordinates so it can be tested without a display. The
point is that a playtest is not limited to whichever layout happened to ship —
being able to build the setup you are curious about, including the ones that
feel bad, is where the answer usually is.
"""

from __future__ import annotations

import math

from .field import Node
from .room import Room

DEFAULT_NODE_RADIUS = 240.0
DEFAULT_CORE_RADIUS = 18.0

MIN_NODE_RADIUS = 40.0
MAX_NODE_RADIUS = 900.0
RADIUS_STEP = 10.0

MIN_CORE_RADIUS = 4.0
CORE_STEP = 2.0
# A core larger than half the influence radius leaves no room to orbit.
CORE_TO_RADIUS_LIMIT = 0.5

GRAB_PADDING = 12.0  # forgiveness around the core when grabbing with a mouse


class RoomEditor:
    """Indices, not Node objects, are used to track the dragged node. `Node` is
    a frozen dataclass, so it compares by value — two nodes placed at the same
    spot with the same radii are `==`, and `list.index()` / `list.remove()`
    would silently act on the wrong one."""

    def __init__(self, room: Room) -> None:
        self.room = room
        self._drag_index: int | None = None

    @property
    def dragging(self) -> Node | None:
        if self._drag_index is None:
            return None
        return self.room.nodes[self._drag_index]

    def _index_at(self, x: float, y: float, reach: str) -> int | None:
        """reach='core' for grab/delete, reach='influence' for hover."""
        best: int | None = None
        best_distance = math.inf
        for index, node in enumerate(self.room.nodes):
            distance = math.hypot(node.x - x, node.y - y)
            limit = (node.core_radius + GRAB_PADDING) if reach == "core" else node.radius
            if distance <= limit and distance < best_distance:
                best = index
                best_distance = distance
        return best

    def hovered(self, x: float, y: float) -> Node | None:
        index = self._index_at(x, y, "influence")
        return None if index is None else self.room.nodes[index]

    def grab(self, x: float, y: float) -> bool:
        self._drag_index = self._index_at(x, y, "core")
        return self._drag_index is not None

    def drag(self, x: float, y: float) -> None:
        if self._drag_index is None:
            return
        node = self.room.nodes[self._drag_index]
        self.room.nodes[self._drag_index] = Node(
            x=x, y=y, radius=node.radius, core_radius=node.core_radius
        )

    def release(self) -> None:
        self._drag_index = None

    def add(self, x: float, y: float) -> Node:
        node = Node(x=x, y=y,
                    radius=DEFAULT_NODE_RADIUS,
                    core_radius=DEFAULT_CORE_RADIUS)
        self.room.nodes.append(node)
        return node

    def delete(self, x: float, y: float) -> bool:
        index = self._index_at(x, y, "core")
        if index is None:
            return False
        self.room.nodes.pop(index)
        if self._drag_index is not None:
            if self._drag_index == index:
                self._drag_index = None
            elif self._drag_index > index:
                self._drag_index -= 1
        return True

    def resize_radius(self, x: float, y: float, direction: int) -> bool:
        index = self._index_at(x, y, "influence")
        if index is None:
            return False
        node = self.room.nodes[index]
        radius = max(MIN_NODE_RADIUS,
                     min(MAX_NODE_RADIUS, node.radius + RADIUS_STEP * direction))
        core = min(node.core_radius, radius * CORE_TO_RADIUS_LIMIT)
        self.room.nodes[index] = Node(x=node.x, y=node.y,
                                      radius=radius, core_radius=core)
        return True

    def resize_core(self, x: float, y: float, direction: int) -> bool:
        index = self._index_at(x, y, "influence")
        if index is None:
            return False
        node = self.room.nodes[index]
        ceiling = node.radius * CORE_TO_RADIUS_LIMIT
        core = max(MIN_CORE_RADIUS,
                   min(ceiling, node.core_radius + CORE_STEP * direction))
        self.room.nodes[index] = Node(x=node.x, y=node.y,
                                      radius=node.radius, core_radius=core)
        return True
