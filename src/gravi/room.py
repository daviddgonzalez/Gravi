"""Room data: where the player starts, which nodes exist, and the bounds.

In slice 1 a room is hand-placed and edited in-session. From slice 3 this is
what the chamber generator emits, so it stays plain data with no behaviour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from .chamber import Chamber, ChamberParams
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


class LabChamber(Chamber):
    """A room seen as a chamber. Identical in every respect except where a run
    opens: the room was authored around its own spawn point, and dropping the
    player on the corridor's centre lane instead can drop them straight onto a
    core the author put there deliberately."""

    def spawn(self) -> tuple[float, float]:
        return self.room_spawn


def room_as_chamber(room: Room) -> LabChamber:
    """A hand-authored room, seen as one chamber: entry at the top-centre,
    gravity down the room, depth the room's height, walls its sides.

    The editor and the slice 1 room stay useful for authoring a node field,
    and they do it through the one `World` everything else runs on. A second
    simulation path would break core spec 8.1 on the day it was written.
    """
    chamber = LabChamber(
        index=0,
        entry=(room.width / 2.0, 0.0),
        direction=(0.0, 1.0),
        turn=0,                 # a lab is for authoring a field, not flipping
        nodes=tuple(room.nodes),
        params=ChamberParams(depth=room.height, half_width=room.width / 2.0),
    )
    object.__setattr__(chamber, "room_spawn", tuple(room.spawn))
    return chamber


class LabChain:
    """The chain a lab runs on: one chamber, looped.

    Crossing its arrow puts the player back at its entrance rather than
    generating a corridor, so a node field can be flown at repeatedly while it
    is being edited. It is a `ChamberChain` only in the parts `World` touches;
    everything structural about streaming is deliberately absent.
    """

    def __init__(self, room: Room) -> None:
        self.room = room
        self.outlines: list[tuple[tuple[float, float], ...]] = []
        self.at = 0
        self._chamber = room_as_chamber(room)
        self.params = self._chamber.params

    def refresh(self) -> None:
        """Rebuild from the room, so an edit shows up in the physics. Cheap:
        one chamber, and only called once a frame."""
        self._chamber = room_as_chamber(self.room)
        self.params = self._chamber.params

    @property
    def current(self) -> LabChamber:
        return self._chamber

    def by_index(self, index: int) -> LabChamber | None:
        return self._chamber if index == self.at else None

    def ensure_ahead(self, count: int | None = None) -> None:
        return None

    def advance(self) -> LabChamber:
        """No outline is retained: a lab has no route to draw a map of."""
        return self._chamber

    def nodes_near(self) -> list[tuple[int, int, Node]]:
        return [(self.at, i, node) for i, node in enumerate(self._chamber.nodes)]
