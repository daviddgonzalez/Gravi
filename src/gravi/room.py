"""Room data: where the player starts, which nodes exist, and the bounds.

In slice 1 a room is hand-placed and edited in-session. From slice 3 this is
what the chamber generator emits, so it stays plain data with no behaviour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from .field import Node


@dataclass
class Room:
    spawn: tuple[float, float]
    nodes: list[Node] = dc_field(default_factory=list)
    width: float = 1280.0
    height: float = 720.0

    def to_dict(self) -> dict:
        return {
            "spawn": list(self.spawn),
            "width": self.width,
            "height": self.height,
            "nodes": [
                {"x": n.x, "y": n.y, "radius": n.radius, "core_radius": n.core_radius}
                for n in self.nodes
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Room":
        return cls(
            spawn=(float(data["spawn"][0]), float(data["spawn"][1])),
            width=float(data.get("width", 1280.0)),
            height=float(data.get("height", 720.0)),
            nodes=[
                Node(
                    x=float(n["x"]),
                    y=float(n["y"]),
                    radius=float(n["radius"]),
                    core_radius=float(n["core_radius"]),
                )
                for n in data.get("nodes", [])
            ],
        )


def load_room(path: str | Path) -> Room:
    with open(path, "r", encoding="utf-8") as handle:
        return Room.from_dict(json.load(handle))


def save_room(room: Room, path: str | Path) -> bool:
    """Write `room` to `path`. Returns False instead of raising when the write
    fails — the browser build has no writable filesystem and must not crash on
    a save keypress."""
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(room.to_dict(), handle, indent=2)
        return True
    except OSError:
        return False
