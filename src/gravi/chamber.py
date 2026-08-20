"""Chamber geometry, generation, and the streamed chain.

A chamber is a box in ITS OWN frame: origin at the entrance line's centre,
+direction into the chamber (which is the gravity direction on entry), and
+perp(direction) across it. Chambers chain by placing the next entrance at the
previous exit, so the arrow is the seam — every chamber has a known entry
vector and a known exit condition, which is what lets chambers be generated
independently and still be guaranteed to connect (core spec 3.1).

The exit arrow spans the chamber's FULL far side. You cross one nearly every
time; what varies is WHERE on it you cross. That matters more than it looks:
a 90 degree turn maps the old lateral axis onto the new depth axis, so the
offset at which you crossed becomes your entry DEPTH in the next chamber, and
your lateral offset there is always exactly zero (slice 2 spec 4.3). Crossing
wide starts you deep and skips part of the next node field; crossing short
starts you behind the entrance with further to fall.

The hard corollary of entering at offset zero: every player enters every
chamber on the centre line, so the centre lane MUST be clear of cores while
influence rings still reach across it — always something to grab in the lane,
never anything to hit.

Never import pygame here (see tests/test_purity.py).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .field import Node

QUARTER = math.pi / 2

Vec = tuple[float, float]


def rot(v: Vec, a: float) -> Vec:
    """Standard rotation matrix. NOTE the direction: a direction whose
    gravity-angle is phi maps to phi - a, not phi + a. Every sign bug in this
    subsystem is a rediscovery of that fact."""
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def perp(d: Vec) -> Vec:
    return (-d[1], d[0])


@dataclass(frozen=True)
class ChamberParams:
    """Fixed dimensions for the one slice 2 archetype. Slice 3 replaces this
    with a sampled parameter box (core spec 4.1) — do not grow it here.

    depth is the flip-frequency knob: it sets how long the player spends
    between arrows at identical physics. The prototype's first value of 1150
    produced ~26 gravity swaps per minute, which playtested as too hard to
    read; 1600 gives ~8.
    """

    depth: float = 1600.0
    half_width: float = 460.0
    lane_clear: float = 110.0       # minimum |offset| of any core from the lane
    side_grace: float = 90.0        # slop past the side wall before death
    node_min_gap: float = 260.0     # keep cores apart, not a minefield
    entry_clear: float = 220.0      # no nodes right on top of the entrance
    exit_clear: float = 200.0
    radius_min: float = 190.0
    radius_max: float = 280.0
    core_min: float = 12.0
    core_max: float = 20.0
    nodes_per_depth: float = 1.0 / 420.0
    keep_behind: int = 3
    generate_ahead: int = 4
    # Gravity turns every turn_gap_min..turn_gap_max chambers; the ones between
    # run straight through. Turning at every single arrow is what made the
    # corridor exhausting to read, and per amendment A1 the rate is a comfort
    # constant, so this is a cadence chosen once, not a difficulty curve.
    turn_gap_min: int = 3
    turn_gap_max: int = 7


@dataclass(frozen=True)
class Chamber:
    index: int
    entry: Vec
    direction: Vec                  # unit; equals gravity direction on entry
    turn: int                       # +1 / -1 quarter turns the exit arrow applies
    nodes: tuple[Node, ...]
    params: ChamberParams

    @property
    def perp(self) -> Vec:
        return perp(self.direction)

    @property
    def exit_center(self) -> Vec:
        return self.world(self.params.depth, 0.0)

    @property
    def next_direction(self) -> Vec:
        return rot(self.direction, self.turn * QUARTER)

    def world(self, t: float, u: float) -> Vec:
        px, py = self.perp
        return (self.entry[0] + self.direction[0] * t + px * u,
                self.entry[1] + self.direction[1] * t + py * u)

    def local(self, x: float, y: float) -> Vec:
        dx = x - self.entry[0]
        dy = y - self.entry[1]
        px, py = self.perp
        return (dx * self.direction[0] + dy * self.direction[1], dx * px + dy * py)

    def arrow_endpoints(self) -> tuple[Vec, Vec]:
        w = self.params.half_width
        return (self.world(self.params.depth, w), self.world(self.params.depth, -w))

    def spawn(self) -> Vec:
        """Where a run opens in this chamber: on the centre lane, just inside
        the entrance. A hand-authored lab chamber overrides this, because its
        room was authored around a spawn of its own."""
        return self.world(60.0, 0.0)

    def outline(self) -> tuple[Vec, Vec, Vec, Vec]:
        """The four corners in world space. Retained after the chamber is
        culled, because the end-of-run path map needs the route's geometry."""
        d, w = self.params.depth, self.params.half_width
        return (self.world(0.0, -w), self.world(d, -w),
                self.world(d, w), self.world(0.0, w))


def turn_schedule(seed: int, params: ChamberParams,
                  upto: int) -> dict[int, int]:
    """Which chamber indices turn gravity, and which way, up to `upto`.

    Walked from the start of the run on its own RNG stream rather than sampled
    per chamber, for two reasons. A cadence is a property of the run — "a turn
    every three to seven chambers" cannot be decided by looking at one chamber
    alone — and S7's validator has to reproduce the same corridor from the seed
    alone (core spec 8.1), so where the turns land must not depend on how far
    the player happened to fly or on what order chambers were generated in.
    """
    rng = random.Random(f"{seed}:turn-cadence")
    low, high = int(params.turn_gap_min), int(params.turn_gap_max)
    schedule: dict[int, int] = {}
    at = rng.randint(low, high)
    while at <= upto:
        schedule[at] = 1 if rng.random() < 0.5 else -1
        at += rng.randint(low, high)
    return schedule


def make_chamber(index: int, entry: Vec, direction: Vec,
                 params: ChamberParams, seed: int | None = None,
                 rng: random.Random | None = None,
                 turn: int | None = None) -> Chamber:
    """One chamber of the single slice 2 archetype. Either pass an `rng` (the
    chain does, so the whole chain is one deterministic stream) or a `seed`.

    `turn` is supplied by the chain from its cadence schedule. Left None it is
    sampled as a coin flip, which is what a chamber built on its own for a test
    wants: a turning chamber, without a run around it to give it a cadence."""
    if rng is None:
        rng = random.Random(seed)

    count = max(3, round(params.depth * params.nodes_per_depth)) + rng.randrange(2)
    span = params.half_width - 130.0 - params.lane_clear
    nodes: list[Node] = []
    guard = 0
    while len(nodes) < count and guard < 200:
        guard += 1
        t = params.entry_clear + rng.random() * (params.depth - params.entry_clear - params.exit_clear)
        side = -1.0 if rng.random() < 0.5 else 1.0
        # Alternate a lane anchor with a wide node. An anchor sits close enough
        # that its influence ring certainly crosses the centre lane, because
        # sampling offsets uniformly across the whole span produces chambers
        # with nothing grabbable from the lane at all -- seed 20's chamber 3
        # was four nodes, none of them reaching. Clear of cores is not the same
        # as reachable, and the entry lane must be both.
        anchor = len(nodes) % 2 == 0
        reach = max(0.0, min(params.radius_min - 20.0, params.lane_clear + span) - params.lane_clear)
        u = side * (params.lane_clear + rng.random() * (reach if anchor else span))
        px, py = perp(direction)
        x = entry[0] + direction[0] * t + px * u
        y = entry[1] + direction[1] * t + py * u
        if any(math.hypot(n.x - x, n.y - y) < params.node_min_gap for n in nodes):
            continue
        nodes.append(Node(
            x=x, y=y,
            radius=params.radius_min + rng.random() * (params.radius_max - params.radius_min),
            core_radius=params.core_min + rng.random() * (params.core_max - params.core_min),
        ))

    if turn is None:
        turn = 1 if rng.random() < 0.5 else -1
    return Chamber(index=index, entry=entry, direction=direction, turn=int(turn),
                   nodes=tuple(nodes), params=params)


class ChamberChain:
    """The streamed corridor: generate ahead, retain a few behind, and keep a
    light outline of every chamber already cleared."""

    def __init__(self, seed: int, params: ChamberParams | None = None,
                 start: Vec = (0.0, 0.0), direction: Vec = (0.0, 1.0)) -> None:
        self.seed = seed
        self.params = params or ChamberParams()
        self._rng = random.Random(seed)
        self.chambers: list[Chamber] = []
        self.outlines: list[tuple[Vec, ...]] = []
        self.at = 0
        self._turns: dict[int, int] = {}
        self._turns_upto = -1
        first = make_chamber(0, start, direction, self.params, rng=self._rng,
                             turn=self._turn_for(0))
        self.chambers.append(first)
        self.ensure_ahead()

    def _turn_for(self, index: int) -> int:
        """0 for a straight chamber. The schedule is extended in blocks rather
        than rebuilt per chamber, and it is keyed off the seed, so it is the
        same whether a run is generated in one go or a chamber at a time."""
        if index > self._turns_upto:
            self._turns_upto = index + 64
            self._turns = turn_schedule(self.seed, self.params, self._turns_upto)
        return self._turns.get(index, 0)

    @property
    def current(self) -> Chamber:
        return self.chambers[self.at - self._culled]

    def ensure_ahead(self, count: int | None = None) -> None:
        want = self.at + (count if count is not None else self.params.generate_ahead)
        while self.chambers[-1].index < want:
            last = self.chambers[-1]
            self.chambers.append(make_chamber(
                last.index + 1, last.exit_center, last.next_direction,
                self.params, rng=self._rng, turn=self._turn_for(last.index + 1)))

    def advance(self) -> Chamber:
        """The player crossed the current chamber's arrow. Returns the chamber
        just cleared, whose outline is retained for the path map."""
        cleared = self.current
        self.outlines.append(cleared.outline())
        self.at += 1
        self.ensure_ahead()
        self._cull()
        return cleared

    def nodes_near(self) -> list[tuple[int, int, Node]]:
        """(chamber index, node index, node) for the current chamber and its
        two neighbours. Rings reach across the seam, so the chamber behind is
        still grabbable and still lethal."""
        out: list[tuple[int, int, Node]] = []
        for index in range(max(0, self.at - 1), self.at + 2):
            ch = self.by_index(index)
            if ch is None:
                continue
            for i, node in enumerate(ch.nodes):
                out.append((index, i, node))
        return out

    def by_index(self, index: int) -> Chamber | None:
        offset = index - self._culled
        if 0 <= offset < len(self.chambers):
            return self.chambers[offset]
        return None

    @property
    def _culled(self) -> int:
        return self.chambers[0].index

    def _cull(self) -> None:
        while self.chambers[0].index < self.at - self.params.keep_behind:
            self.chambers.pop(0)
