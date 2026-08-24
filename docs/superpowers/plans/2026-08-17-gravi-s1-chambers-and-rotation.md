# Session S1 — Slice 2: chambers, gravity vector, camera rotation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**You are session S1 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` for the house rules and what the other sessions are doing before you start.

**Goal:** Turn Gravi from one hand-placed room with downward gravity into a streamed chain of chambers whose exit arrows rotate gravity, with a camera that rotates so gravity is always screen-down and a fixed-camera option that never moves at all — then playtest it and record a verdict.

**Architecture:** Two new pure modules (`gravity.py`, `chamber.py`) hold everything the validator and trainer will later need, exactly as `field.py` does today. `sim.World` is rewritten to run on a chamber chain instead of a `Room`, with the speed clamp moved into gravity-relative axes. Rotation happens only at draw time in a new `render/camera.py`; world coordinates never rotate, because the offline validator must simulate the same numbers the game does (core spec §8.1).

**Tech stack:** Python 3.12, pygame-ce, pytest. No new runtime dependencies — everything must survive WebAssembly.

**Source of truth:**
- Design: `docs/superpowers/specs/2026-08-13-gravi-slice-2-gravity-and-camera-design.md` (read it fully before task 1)
- Parent: `docs/superpowers/specs/2026-08-11-gravi-core-design.md` §3.1–3.3, §8.1, §8.6
- Reference implementation: `proto/terrain-demo.html` — this is a **working prototype of everything in this plan**. When a detail is ambiguous, read the JS. It has already been playtested; the constants in it are the tuned ones.

**Scope decision already made (spec §2):** slice 2 includes the minimum chamber work — one archetype, fixed dimensions, streaming. Archetype variety, the parameter box, validation, difficulty measurement, branching, hazards and node depletion are **not** yours; they belong to sessions S6/S7 off the S2 design. If you find yourself writing a second archetype, stop.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `src/gravi/gravity.py` | create | Eased quarter-turn gravity state. Pure — no pygame. |
| `src/gravi/chamber.py` | create | Chamber geometry, seeded generation, the streamed chain. Pure — no pygame. |
| `src/gravi/render/camera.py` | create | World→screen transform: rotation + follow. |
| `src/gravi/sim.py` | rewrite | Runs on a chamber chain; gravity-relative clamps; arrow crossing; death. |
| `src/gravi/render/neon.py` | modify | Every draw call takes a camera; add chamber outline and arrow bar. |
| `src/gravi/config.py` | modify | `gravity_y` → `gravity`; add `flip_duration`, `chamber_depth`, `chamber_half_width`. |
| `main.py` | modify | Wire the chain, the camera toggle, the run HUD, respawn. |
| `src/gravi/room.py`, `src/gravi/editor.py` | keep | Unchanged. Reachable through `--room` lab mode only (task 8). |
| `presets/default.json` | modify | Follows the `gravity` rename. |
| `tests/test_gravity.py`, `test_chamber.py`, `test_camera.py` | create | |
| `tests/test_sim.py`, `test_purity.py`, `test_neon.py`, `test_config.py` | modify | |

---

## The two sign conventions that will bite you

Both are written down here because both bit the prototype.

**1. `rot(d, a)` turns a direction from angle φ to angle φ − a.**

Directions are stored as `(x, y)` and their gravity-angle is `phi = atan2(x, y)`, so that `phi = 0` is world-down `(0, 1)`. With the standard rotation matrix

```python
def rot(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)
```

a direction `d = (sin φ, cos φ)` maps to `(sin(φ − a), cos(φ − a))`. So when a chamber's exit turns the corridor by `turn` quarter-turns, gravity must flip by **`-turn`** quarter-turns. Get this backwards and the world spins the wrong way on every single flip — which looks *almost* right, which is why it survived a playtest in the prototype.

**2. Increasing `phi` is counter-clockwise on screen** (screen y points down; `phi` sweeps gravity from 6 o'clock toward 3 o'clock). So the spec's "a 180° flip takes the clockwise path" means **decreasing** `phi`, i.e. `flip_by(-2)`.

---

## Task 1: `gravity.py` — the eased quarter-turn

**Goal:** One pure module owning gravity direction as a single eased scalar, with an integer target that cannot drift.

**Files:**
- Create: `src/gravi/gravity.py`
- Test: `tests/test_gravity.py`
- Modify: `tests/test_purity.py`

**Acceptance criteria:**
- [ ] `GravityState.angle` eases from the old angle to the new one over `flip_duration` and lands exactly on the target
- [ ] After 500 alternating flips the settled angle is exactly `target_turns * pi/2` — no float accumulation drift
- [ ] `flip_to` on a 180° turn takes the clockwise path (phi decreases)
- [ ] `settle(turns)` jumps to an orientation with no ease, for spawning
- [ ] `gravity.py` imports nothing but `math` and `dataclasses`

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_gravity.py tests/test_purity.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gravity.py
import math

import pytest

from gravi.gravity import QUARTER, GravityState, ease_in_out


def test_starts_settled_pointing_world_down():
    g = GravityState(flip_duration=0.3)
    assert g.settled
    assert g.direction() == pytest.approx((0.0, 1.0), abs=1e-12)


def test_flip_eases_and_lands_exactly_on_target():
    g = GravityState(flip_duration=0.3)
    g.flip_by(1)
    assert not g.settled
    assert g.angle == pytest.approx(0.0)
    for _ in range(300):
        g.advance(1.0 / 240.0)
    assert g.settled
    assert g.angle == pytest.approx(QUARTER, abs=1e-12)
    assert g.direction() == pytest.approx((1.0, 0.0), abs=1e-12)


def test_ease_is_monotonic_and_clamped():
    assert ease_in_out(-1.0) == 0.0
    assert ease_in_out(0.0) == 0.0
    assert ease_in_out(1.0) == 1.0
    assert ease_in_out(2.0) == 1.0
    values = [ease_in_out(i / 20.0) for i in range(21)]
    assert values == sorted(values)


def test_integer_target_never_drifts():
    """Hundreds of flips accumulating += pi/2 as floats would drift. The
    target is an integer count of quarter turns, so it cannot."""
    g = GravityState(flip_duration=0.05)
    for i in range(500):
        g.flip_by(1 if i % 3 else -1)
        for _ in range(20):
            g.advance(1.0 / 240.0)
        assert g.settled
    assert g.angle == g.target_turns * QUARTER
    assert isinstance(g.target_turns, int)


def test_half_turn_goes_clockwise():
    """Shortest path is ambiguous for 180 degrees, so the convention is
    clockwise on screen, which is DECREASING phi (screen y points down)."""
    g = GravityState(flip_duration=0.3)
    g.flip_to(2)
    g.advance(0.15)
    assert g.angle < 0.0
    for _ in range(300):
        g.advance(1.0 / 240.0)
    assert g.angle == pytest.approx(-2 * QUARTER, abs=1e-12)
    assert g.direction() == pytest.approx((0.0, -1.0), abs=1e-9)


def test_flip_to_takes_the_short_way_round():
    g = GravityState(flip_duration=0.1)
    g.flip_to(3)          # three quarter turns one way, one the other
    assert g.target_turns == -1


def test_zero_duration_snaps():
    g = GravityState(flip_duration=0.0)
    g.flip_by(1)
    assert g.settled
    assert g.angle == pytest.approx(QUARTER)


def test_settle_puts_gravity_on_an_orientation_with_no_ease():
    """A run must never open mid-flip, so spawning into a chamber sets
    gravity to that chamber's orientation outright."""
    g = GravityState(flip_duration=0.3)
    g.flip_by(1)
    g.settle(-1)
    assert g.settled
    assert g.target_turns == -1
    assert g.angle == pytest.approx(-QUARTER)


def test_vector_scales_the_direction():
    g = GravityState(flip_duration=0.3)
    assert g.vector(500.0) == pytest.approx((0.0, 500.0), abs=1e-12)
```

Add to `tests/test_purity.py` alongside the existing checks:

```python
def test_gravity_module_is_pure():
    source = (SRC / "gravity.py").read_text(encoding="utf-8")
    assert "pygame" not in source
```

- [ ] **Step 2: Run them and watch them fail**

Run: `PYTHONPATH= .venv/bin/pytest tests/test_gravity.py -v`
Expected: `ModuleNotFoundError: No module named 'gravi.gravity'`

- [ ] **Step 3: Write the module**

```python
"""Gravity direction as one eased scalar.

Gravity direction and camera rotation are the SAME number (slice 2 spec
section 3.1). Because the camera rotation is exactly the rotation that carries
the gravity vector onto screen-down, gravity is straight down on screen at
every instant, including mid-turn — not merely at the endpoints. Snapping
gravity at the crossing and easing only the camera was rejected: it leaves
0.2 s in which the force felt and the screen read disagree, at precisely the
moment the player is most disoriented.

The flip TARGET is an integer count of quarter turns; only the eased CURRENT
angle is a float. Hundreds of flips accumulating `+= pi/2` would drift.

phi = 0 is world-down. Increasing phi sweeps gravity from 6 o'clock toward
3 o'clock, which is counter-clockwise on screen — so the spec's clockwise
convention for 180 degree flips means DECREASING phi.

Never import pygame here (see tests/test_purity.py).
"""

from __future__ import annotations

import math

QUARTER = math.pi / 2

Vec = tuple[float, float]


def ease_in_out(t: float) -> float:
    """Raised cosine on [0, 1], clamped outside it. Zero slope at both ends,
    which is what stops a flip from starting and stopping with a jerk."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 0.5 - 0.5 * math.cos(math.pi * t)


class GravityState:
    """Eased quarter-turn gravity. `angle` is the only float that moves."""

    def __init__(self, quarter_turns: int = 0, flip_duration: float = 0.3) -> None:
        self.target_turns = int(quarter_turns)
        self.flip_duration = flip_duration
        self.angle = self.target_angle
        self._from_angle = self.angle
        self._t = 1.0

    @property
    def target_angle(self) -> float:
        return self.target_turns * QUARTER

    @property
    def settled(self) -> bool:
        return self._t >= 1.0

    def flip_by(self, quarter_turns: int) -> None:
        """Turn by a signed number of quarter turns, from wherever the ease
        currently is — so a flip that interrupts another flip is continuous."""
        self._from_angle = self.angle
        self.target_turns += int(quarter_turns)
        if self.flip_duration <= 0.0:
            self._t = 1.0
            self.angle = self.target_angle
        else:
            self._t = 0.0

    def flip_to(self, quarter_turns: int) -> None:
        """Turn to an absolute quarter-turn index by the shortest path. A
        180 degree turn is ambiguous, so it goes clockwise (phi decreasing)."""
        delta = (int(quarter_turns) - self.target_turns) % 4
        if delta == 3:
            delta = -1
        elif delta == 2:
            delta = -2      # clockwise by convention
        self.flip_by(delta)

    def settle(self, quarter_turns: int) -> None:
        """Jump straight to an orientation with no ease. Spawning uses this:
        a run must never open mid-flip."""
        self.target_turns = int(quarter_turns)
        self.angle = self.target_angle
        self._from_angle = self.angle
        self._t = 1.0

    def advance(self, dt: float) -> None:
        if self._t >= 1.0:
            return
        self._t = min(1.0, self._t + dt / self.flip_duration)
        span = self.target_angle - self._from_angle
        self.angle = self._from_angle + span * ease_in_out(self._t)
        if self._t >= 1.0:
            self.angle = self.target_angle

    def direction(self) -> Vec:
        return (math.sin(self.angle), math.cos(self.angle))

    def vector(self, magnitude: float) -> Vec:
        dx, dy = self.direction()
        return (dx * magnitude, dy * magnitude)
```

- [ ] **Step 4: Run the tests again**

Run: `PYTHONPATH= .venv/bin/pytest tests/test_gravity.py tests/test_purity.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/gravi/gravity.py tests/test_gravity.py tests/test_purity.py
git commit -m "feat(gravity): eased quarter-turn gravity with an integer target"
```

---

## Task 2: `chamber.py` — geometry, generation, and the streamed chain

**Goal:** A chamber is a box in its own frame; chambers chain by placing the next entrance at the previous exit; the chain generates ahead and retains a few behind.

**Files:**
- Create: `src/gravi/chamber.py`
- Test: `tests/test_chamber.py`
- Modify: `tests/test_purity.py`

**Read first:** spec §4 in full, and `proto/terrain-demo.html` lines 275–356 (`makeChamber`, `generate`, `extend`) — this task is that code, ported and tested.

**Acceptance criteria:**
- [ ] `Chamber.local(x, y)` returns `(t, u)`: depth into the chamber and lateral offset, both in the chamber's own frame
- [ ] Over 300 seeds, **no generated core lies within `core_radius + player_radius + margin` of the centre lane** (spec §4.3 — this is the property that stops a do-nothing run dying in 0.8 s)
- [ ] Chambers chain with no gap: chamber *n+1*'s entry equals chamber *n*'s exit centre, and its direction is chamber *n*'s `next_direction`
- [ ] The same seed always produces the identical chain (determinism, core spec §9)
- [ ] `ChamberChain.ensure_ahead()` keeps at least 3 chambers generated past the current one; cleared chamber outlines are retained, not discarded
- [ ] `chamber.py` imports only `math`, `random`, `dataclasses` and `.field`

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_chamber.py tests/test_purity.py -v` → all pass

**Why outlines are retained even though nothing draws them yet:** core spec §6 requires the end-of-run path map to draw the whole route, which means the run must retain chamber geometry rather than discarding it behind the camera. Keeping a light outline record from the first commit is free; retrofitting it after streaming has been optimised is not. Session S10 consumes it.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_chamber.py
import math

import pytest

from gravi.chamber import QUARTER, ChamberChain, ChamberParams, make_chamber, rot

PARAMS = ChamberParams()


def test_rot_turns_a_direction_from_phi_to_phi_minus_a():
    """The sign trap from spec 3.3, pinned as an assertion rather than a
    comment. A direction at gravity-angle phi maps to phi - a."""
    down = (0.0, 1.0)
    turned = rot(down, QUARTER)
    assert turned == pytest.approx((-1.0, 0.0), abs=1e-12)
    assert math.atan2(turned[0], turned[1]) == pytest.approx(-QUARTER)


def test_local_coordinates_are_depth_and_offset():
    ch = make_chamber(0, (0.0, 0.0), (0.0, 1.0), PARAMS, seed=1)
    assert ch.local(0.0, 300.0) == pytest.approx((300.0, 0.0))
    # +perp of down is (-1, 0), so a point to the LEFT is positive offset
    assert ch.local(-50.0, 300.0) == pytest.approx((300.0, 50.0))


def test_world_and_local_round_trip():
    ch = make_chamber(3, (120.0, -40.0), (1.0, 0.0), PARAMS, seed=7)
    x, y = ch.world(400.0, -120.0)
    assert ch.local(x, y) == pytest.approx((400.0, -120.0))


def test_arrow_spans_the_full_far_side():
    ch = make_chamber(0, (0.0, 0.0), (0.0, 1.0), PARAMS, seed=2)
    a, b = ch.arrow_endpoints()
    assert math.dist(a, b) == pytest.approx(2 * PARAMS.half_width)
    for point in (a, b):
        t, _ = ch.local(*point)
        assert t == pytest.approx(PARAMS.depth)


def test_no_core_lies_in_the_centre_lane():
    """Spec 4.3: every chamber is entered at lateral offset exactly zero, so
    a core on the axis is an unavoidable death for a player who does nothing.
    The prototype shipped one at offset 18 and killed every run in 0.8 s."""
    clearance = PARAMS.lane_clear
    for seed in range(300):
        chain = ChamberChain(seed=seed, params=PARAMS)
        for ch in chain.chambers:
            for node in ch.nodes:
                _, u = ch.local(node.x, node.y)
                assert abs(u) >= clearance, (seed, ch.index, u)


def test_influence_rings_still_reach_the_lane():
    """Clear of cores is not enough — there must be something to grab from
    the lane, or the clearance rule just makes an empty corridor."""
    for seed in range(50):
        chain = ChamberChain(seed=seed, params=PARAMS)
        for ch in chain.chambers:
            reaching = [n for n in ch.nodes if abs(ch.local(n.x, n.y)[1]) < n.radius]
            assert reaching, (seed, ch.index)


def test_chambers_chain_without_gaps():
    chain = ChamberChain(seed=11, params=PARAMS)
    chain.ensure_ahead(10)
    for a, b in zip(chain.chambers, chain.chambers[1:]):
        assert b.entry == pytest.approx(a.exit_center)
        assert b.direction == pytest.approx(a.next_direction)
        assert b.index == a.index + 1


def test_turns_are_quarter_turns_only():
    chain = ChamberChain(seed=5, params=PARAMS)
    chain.ensure_ahead(20)
    assert {ch.turn for ch in chain.chambers} <= {1, -1}


def test_same_seed_same_chain():
    a = ChamberChain(seed=99, params=PARAMS)
    b = ChamberChain(seed=99, params=PARAMS)
    a.ensure_ahead(12)
    b.ensure_ahead(12)
    assert [ch.entry for ch in a.chambers] == [ch.entry for ch in b.chambers]
    assert [[(n.x, n.y, n.radius, n.core_radius) for n in ch.nodes] for ch in a.chambers] == \
           [[(n.x, n.y, n.radius, n.core_radius) for n in ch.nodes] for ch in b.chambers]


def test_advance_streams_ahead_and_retains_an_outline_behind():
    chain = ChamberChain(seed=3, params=PARAMS)
    for _ in range(8):
        chain.advance()
    assert chain.by_index(chain.at + 3) is not None      # still generating ahead
    assert chain.by_index(chain.at - 4) is None          # and culling behind
    assert len(chain.outlines) == 8          # one per cleared chamber, for the path map
    assert chain.current.index == 8


def test_nodes_near_covers_the_neighbours_only():
    chain = ChamberChain(seed=4, params=PARAMS)
    chain.ensure_ahead(6)
    chain.at = 3
    indices = {c for c, _, _ in chain.nodes_near()}
    assert indices == {2, 3, 4}
```

Add to `tests/test_purity.py`:

```python
def test_chamber_module_is_pure():
    source = (SRC / "chamber.py").read_text(encoding="utf-8")
    assert "pygame" not in source
```

- [ ] **Step 2: Run them and watch them fail**

Run: `PYTHONPATH= .venv/bin/pytest tests/test_chamber.py -v`
Expected: `ModuleNotFoundError: No module named 'gravi.chamber'`

- [ ] **Step 3: Write the module**

```python
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
from dataclasses import dataclass, field as dc_field

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

    def outline(self) -> tuple[Vec, Vec, Vec, Vec]:
        """The four corners in world space. Retained after the chamber is
        culled, because the end-of-run path map needs the route's geometry."""
        d, w = self.params.depth, self.params.half_width
        return (self.world(0.0, -w), self.world(d, -w),
                self.world(d, w), self.world(0.0, w))


def make_chamber(index: int, entry: Vec, direction: Vec,
                 params: ChamberParams, seed: int | None = None,
                 rng: random.Random | None = None) -> Chamber:
    """One chamber of the single slice 2 archetype. Either pass an `rng` (the
    chain does, so the whole chain is one deterministic stream) or a `seed`."""
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
        u = side * (params.lane_clear + rng.random() * span)
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

    turn = 1 if rng.random() < 0.5 else -1
    return Chamber(index=index, entry=entry, direction=direction, turn=turn,
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
        first = make_chamber(0, start, direction, self.params, rng=self._rng)
        self.chambers.append(first)
        self.ensure_ahead()

    @property
    def current(self) -> Chamber:
        return self.chambers[self.at - self._culled]

    def ensure_ahead(self, count: int | None = None) -> None:
        want = self.at + (count if count is not None else self.params.generate_ahead)
        while self.chambers[-1].index < want:
            last = self.chambers[-1]
            self.chambers.append(make_chamber(
                last.index + 1, last.exit_center, last.next_direction,
                self.params, rng=self._rng))

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
```

Note the `nodes_near()` return shape is `(chamber_index, node_index, node)`; the test above unpacks only the first two. Keep the shape — `sim.py` latches by that pair in task 3.

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH= .venv/bin/pytest tests/test_chamber.py tests/test_purity.py -v`
Expected: all PASS. If `test_no_core_lies_in_the_centre_lane` fails, do **not** widen the assertion — the generator is wrong, and this is the exact bug the prototype shipped.

- [ ] **Step 5: Commit**

```bash
git add src/gravi/chamber.py tests/test_chamber.py tests/test_purity.py
git commit -m "feat(chamber): chamber geometry, seeded generation, and the streamed chain"
```

---

## Task 3: `sim.py` — run the world on a chamber chain

**Goal:** `World` steps a point mass through a streamed chamber chain: gravity is a rotating vector, the speed clamp is gravity-relative, crossing the exit arrow advances the chamber and turns gravity, and leaving sideways kills.

**Files:**
- Modify: `src/gravi/sim.py` (rewrite `World`; `charge_from_input` is untouched)
- Modify: `tests/test_sim.py`

**Read first:** slice 2 spec §4.2, §4.3, §6; `proto/terrain-demo.html` lines 436–500 (`step`).

**Acceptance criteria:**
- [ ] At `phi = 0` the clamp is behaviourally identical to slice 1's `vx`/`vy` split
- [ ] `test_gravity_never_taxes_horizontal_carry` passes at `phi ∈ {0°, 90°, 180°, 270°}` with the axes rotated to match — carry is untouched by gravity at **any** orientation
- [ ] Crossing the exit plane inside the span advances the chamber and flips gravity by `-turn` quarter turns
- [ ] Crossing outside the span, drifting past the side wall, or being thrown back out of the entrance all kill
- [ ] Entry lateral offset into the next chamber is always exactly zero (spec §4.3)
- [ ] Core contact anywhere in the three live chambers kills
- [ ] The rope still holds past the rim for attract and breaks at the rim for repel (slice 1 §2.2.1 behaviour, now latched by chamber+node index)
- [ ] `sim.py` still imports no pygame

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/ -v` → all pass (the whole suite; slice 1's tests are the regression net)

**Steps:**

- [ ] **Step 1: Write the failing tests**

Put this helper at the top of `tests/test_sim.py` and rewrite the existing room-based fixtures onto it — the old `Room`-based `World(...)` constructor is gone.

```python
from dataclasses import replace

from gravi.chamber import QUARTER, Chamber, ChamberChain, ChamberParams
from gravi.field import Charge, FieldParams, Node
from gravi.gravity import GravityState
from gravi.sim import World

PARAMS = FieldParams(k_attract=15.0, k_repel=15.0, force_max=4500.0)


def chain_with(nodes, params=None):
    """A deterministic one-archetype chain whose first chamber holds exactly
    the nodes a test cares about."""
    chain = ChamberChain(seed=0, params=params or ChamberParams())
    chain.chambers[0] = replace(chain.chambers[0], nodes=tuple(nodes))
    return chain


def make_world(nodes=(), flip_duration=0.3, **kwargs):
    return World(
        chain=chain_with(nodes),
        params=PARAMS,
        gravity=500.0,
        gravity_state=GravityState(flip_duration=flip_duration),
        player_radius=7.0,
        speed_max=600.0,
        fall_speed_max=600.0,
        **kwargs,
    )
```

```python
def test_clamp_reduces_to_slice_one_at_phi_zero():
    """Spec section 6: the gravity-relative clamp is a strict generalisation
    of slice 1's per-axis split, so at phi = 0 it must do exactly that."""
    w = make_world()
    w.vx, w.vy = 5000.0, 5000.0
    w.step(Charge.NEUTRAL)
    assert w.vx == pytest.approx(600.0)
    assert w.vy == pytest.approx(600.0)


def test_upward_speed_is_never_capped():
    w = make_world()
    w.vy = -5000.0
    w.step(Charge.NEUTRAL)
    assert w.vy < -4000.0


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_gravity_never_taxes_carry_at_any_orientation(turns):
    """The slice 1 finding, re-run rotated. An isotropic clamp bled carry from
    600 to 439 in one second while |v| sat pinned at the cap; the split clamp
    must leave carry untouched no matter which way gravity points."""
    w = make_world(flip_duration=0.0)
    w.gravity_state.flip_by(turns)
    gx, gy = w.gravity_state.direction()
    px, py = gy, -gx
    w.vx, w.vy = px * 600.0, py * 600.0
    for _ in range(240):
        w.step(Charge.NEUTRAL)
        if w.dead:
            break
    carry = w.vx * px + w.vy * py
    assert carry == pytest.approx(600.0, abs=1.0)


def test_crossing_the_arrow_advances_and_turns_gravity():
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    turn = ch.turn
    w.x, w.y = ch.world(ch.params.depth - 1.0, 0.0)
    w.vx, w.vy = ch.direction[0] * 600.0, ch.direction[1] * 600.0
    for _ in range(10):
        w.step(Charge.NEUTRAL)
        if w.chain.at == 1:
            break
    assert w.chain.at == 1
    assert not w.dead
    assert w.gravity_state.target_turns == -turn      # spec 3.3's sign trap
    assert w.gravity_state.direction() == pytest.approx(w.chain.current.direction, abs=1e-9)


def test_entry_lateral_offset_is_always_zero():
    """Spec 4.3: the old lateral axis becomes the new depth axis, so where you
    crossed becomes how deep you start — and offset is always exactly zero."""
    for u in (-300.0, -50.0, 0.0, 120.0, 400.0):
        w = make_world(flip_duration=0.0)
        ch = w.chain.current
        w.x, w.y = ch.world(ch.params.depth - 1.0, u)
        w.vx, w.vy = ch.direction[0] * 600.0, ch.direction[1] * 600.0
        for _ in range(10):
            w.step(Charge.NEUTRAL)
            if w.chain.at == 1:
                break
        assert not w.dead, u
        _, offset = w.chain.current.local(w.x, w.y)
        assert offset == pytest.approx(0.0, abs=1e-9), u


def test_crossing_outside_the_span_kills():
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    w.x, w.y = ch.world(ch.params.depth - 1.0, ch.params.half_width + 5.0)
    w.vx, w.vy = ch.direction[0] * 600.0, ch.direction[1] * 600.0
    for _ in range(10):
        w.step(Charge.NEUTRAL)
    assert w.dead
    assert w.chain.at == 0


def test_leaving_the_chamber_sideways_kills():
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    w.x, w.y = ch.world(400.0, 0.0)
    px, py = ch.perp
    w.vx, w.vy = px * 600.0, py * 600.0
    for _ in range(600):
        w.step(Charge.NEUTRAL)
        if w.dead:
            break
    assert w.dead


def test_core_contact_kills_in_a_neighbouring_chamber_too():
    w = make_world(flip_duration=0.0)
    node = w.chain.by_index(1).nodes[0]
    w.x, w.y = node.x, node.y
    w.step(Charge.NEUTRAL)
    assert w.dead


def test_distance_accumulates_along_the_actual_path():
    w = make_world()
    start = (w.x, w.y)
    for _ in range(240):
        w.step(Charge.NEUTRAL)
    assert w.distance > math.dist(start, (w.x, w.y)) * 0.99
    assert w.distance > 0.0
```

Keep every slice 1 latch test (`test_attract_rope_holds_past_the_rim`, `test_repel_rope_breaks_at_the_rim`, and friends) — port them onto `make_world([...])` and change nothing else about what they assert.

- [ ] **Step 2: Run and watch them fail**

Run: `PYTHONPATH= .venv/bin/pytest tests/test_sim.py -v`
Expected: `TypeError: World.__init__() got an unexpected keyword argument 'chain'`

- [ ] **Step 3: Rewrite `World`**

Replace the constructor, `reset`, the node lookups, and `step`. The docstring at the top of the module stays — the integrator rationale has not changed. Key shape:

```python
from .chamber import ChamberChain
from .field import Charge, FieldParams, Node, charge_force
from .gravity import GravityState


class World:
    """Mutable simulation state for one run through a chamber chain."""

    def __init__(self, chain: ChamberChain, params: FieldParams, gravity: float,
                 gravity_state: GravityState, player_radius: float,
                 speed_max: float, fall_speed_max: float = math.inf,
                 dt: float = PHYS_DT) -> None:
        self.chain = chain
        self.params = params
        self.gravity = gravity                  # magnitude; direction lives in gravity_state
        self.gravity_state = gravity_state
        self.player_radius = player_radius
        self.speed_max = speed_max
        self.fall_speed_max = fall_speed_max
        self.dt = dt
        self.x = self.y = self.vx = self.vy = 0.0
        self.dead = False
        self.elapsed = 0.0
        self.distance = 0.0
        self.cleared = 0
        self._latch: tuple[int, int] | None = None
        self.reset()

    def reset(self) -> None:
        """Spawn just inside the current chamber's entrance, with gravity
        already settled onto that chamber's direction — a run must never open
        mid-flip."""
        ch = self.chain.current
        self.x, self.y = ch.world(60.0, 0.0)
        self.vx = self.vy = 0.0
        self.dead = False
        self.elapsed = 0.0
        self._latch = None
        self.gravity_state.settle(round(math.atan2(ch.direction[0], ch.direction[1]) / QUARTER))
        self.distance = 0.0
        self.cleared = 0
```

`step` in order — this ordering is load-bearing, keep it:

```python
    def step(self, charge: Charge) -> None:
        self.gravity_state.advance(self.dt)     # gravity keeps easing even while dead
        if self.dead:
            return

        gx, gy = self.gravity_state.direction()
        ax, ay = gx * self.gravity, gy * self.gravity

        node = self._update_latch(charge)
        if node is not None:
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=charge is Charge.ATTRACT)
            ax += fx
            ay += fy

        self.vx += ax * self.dt
        self.vy += ay * self.dt

        # Per-axis clamp in GRAVITY-RELATIVE axes: "fall" along gravity, "carry"
        # perpendicular to it. Leaving these in world axes would silently undo
        # slice 1's carry fix the moment the player is sideways.
        px, py = gy, -gx
        fall = self.vx * gx + self.vy * gy
        carry = self.vx * px + self.vy * py
        if fall > self.fall_speed_max:
            fall = self.fall_speed_max          # downward only; up stays uncapped
        if abs(carry) > self.speed_max:
            carry = math.copysign(self.speed_max, carry)
        self.vx = fall * gx + carry * px
        self.vy = fall * gy + carry * py

        nx = self.x + self.vx * self.dt
        ny = self.y + self.vy * self.dt
        self.distance += math.hypot(nx - self.x, ny - self.y)
        self.x, self.y = nx, ny
        self.elapsed += self.dt

        self._check_bounds()
        if not self.dead:
            self._check_cores()
```

```python
    def _check_bounds(self) -> None:
        ch = self.chain.current
        t, u = ch.local(self.x, self.y)
        if t >= ch.params.depth:
            if abs(u) > ch.params.half_width:
                self.dead = True                # left past the side, not through the arrow
                return
            # rot() carries a direction at angle phi to phi - a, so gravity
            # turns by the NEGATIVE of the corridor's geometric turn.
            self.gravity_state.flip_by(-ch.turn)
            self.chain.advance()
            self.cleared += 1
            self._latch = None                  # no handoff across the seam
        elif abs(u) > ch.params.half_width + ch.params.side_grace:
            self.dead = True
        elif t < -600.0:
            self.dead = True                    # thrown back out of the entrance

    def _check_cores(self) -> None:
        for _, _, node in self.chain.nodes_near():
            if math.hypot(node.x - self.x, node.y - self.y) <= node.core_radius + self.player_radius:
                self.dead = True
                return
```

The latch becomes a `(chamber index, node index)` pair resolved through `chain.by_index`; the *rules* are unchanged from slice 1, so port `_update_latch`, `latched_node`, `active_node` and `_within` verbatim except for how a node is addressed. Keep the slice 1 docstring on `_update_latch` — the asymmetry it explains is still the reason.

- [ ] **Step 4: Run the whole suite**

Run: `PYTHONPATH= .venv/bin/pytest tests/ -v`
Expected: all PASS. `tests/test_editor.py` and `tests/test_field.py` must be untouched by this task — if you had to edit them, you changed something you should not have.

- [ ] **Step 5: Commit**

```bash
git add src/gravi/sim.py tests/test_sim.py
git commit -m "feat(sim): run on a chamber chain with gravity-relative clamps"
```

---

## Task 4: `render/camera.py` — rotation at draw time

**Goal:** One transform that maps world to screen, holding the rotation angle and the follow point, so that world coordinates never rotate.

**Files:**
- Create: `src/gravi/render/camera.py`
- Test: `tests/test_camera.py`

**Read first:** slice 2 spec §5 in full — particularly §5.2, which is a record of two wrong answers already tried.

**Acceptance criteria:**
- [ ] With `angle = 0` and the eye at the origin, `to_screen` is the identity
- [ ] The followed point always lands exactly on the eye point
- [ ] **The invariant:** with the camera rotating, the gravity direction maps to screen-down `(0, 1)` — asserted at every step of a flip, not only at the endpoints
- [ ] In fixed mode the eye is dead centre and **nothing** about the framing moves with gravity
- [ ] `to_world(to_screen(p)) == p`

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_camera.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_camera.py
import math

import pytest

from gravi.gravity import GravityState
from gravi.render.camera import Camera


def test_identity_at_angle_zero():
    cam = Camera.identity()
    assert cam.to_screen(120.0, -45.0) == pytest.approx((120.0, -45.0))


def test_the_followed_point_lands_on_the_eye():
    cam = Camera(1280, 720)
    cam.update(500.0, -300.0, angle=1.1, rotating=True)
    assert cam.to_screen(500.0, -300.0) == pytest.approx(cam.eye)


def test_rotation_carries_gravity_onto_screen_down_at_every_step():
    """Spec 3.3's required test. This invariant is the whole justification for
    rotating the camera at all, and it is the one the prototype got backwards."""
    g = GravityState(flip_duration=0.3)
    cam = Camera(1280, 720)
    g.flip_by(1)
    for _ in range(200):
        g.advance(1.0 / 240.0)
        cam.update(0.0, 0.0, angle=g.angle, rotating=True)
        gx, gy = g.direction()
        sx, sy = cam.direction_to_screen(gx, gy)
        assert (sx, sy) == pytest.approx((0.0, 1.0), abs=1e-9)


def test_fixed_camera_does_not_rotate_and_does_not_pan():
    """Removing rotation is not enough: a fixed camera must have no
    gravity-driven motion of any kind, so the eye is dead centre and stays
    there. Leading in the gravity direction panned the view by up to twice the
    lead distance on every flip, which reads as a moving camera."""
    cam = Camera(1280, 720)
    eyes = []
    for angle in (0.0, 0.4, math.pi / 2, math.pi):
        cam.update(0.0, 0.0, angle=angle, rotating=False)
        eyes.append(cam.eye)
        assert cam.to_screen(100.0, 0.0) == pytest.approx((cam.eye[0] + 100.0, cam.eye[1]))
    assert len(set(eyes)) == 1
    assert eyes[0] == (640.0, 360.0)


def test_rotating_camera_sits_back_from_centre():
    cam = Camera(1280, 720)
    cam.update(0.0, 0.0, angle=0.0, rotating=True)
    assert cam.eye[1] < 360.0        # more of the fall ahead is visible


def test_screen_to_world_round_trips():
    cam = Camera(1280, 720)
    cam.update(310.0, -90.0, angle=0.7, rotating=True)
    assert cam.to_world(*cam.to_screen(12.0, 34.0)) == pytest.approx((12.0, 34.0))
```

- [ ] **Step 2: Run and watch them fail**

Run: `PYTHONPATH= .venv/bin/pytest tests/test_camera.py -v`
Expected: `ModuleNotFoundError: No module named 'gravi.render.camera'`

- [ ] **Step 3: Write the module**

```python
"""World -> screen. Rotation happens here and nowhere else.

World coordinates never rotate. That is not an aesthetic choice: the offline
validator and the trainer must simulate exactly what the game simulates (core
spec 8.1), and a rotating coordinate system would be a second source of truth.

Rotating at draw time is cheap here for a reason specific to Gravi: circles are
rotation-invariant. Nodes, cores, glows and the player are circles, so only
their centre points transform. Only the trail polyline, the beam, the arrow
bars and the chamber outlines need per-point work, and sin/cos are computed
once per frame.

Rejected: rotating the finished frame with pygame.transform.rotate. At
mid-ease angles the output bounding box grows by up to sqrt(2), so it is ~1M
pixels resampled plus an allocation every frame against a frame that costs
1.10 ms — and it resamples rasterised neon, which blurs and crawls the glow,
the exact shimmer that choosing neon was supposed to delete.
"""

from __future__ import annotations

import math

from .. import config

LEAD_FRACTION = 0.12


class Camera:
    def __init__(self, width: int = config.WINDOW_WIDTH,
                 height: int = config.WINDOW_HEIGHT) -> None:
        self.width = width
        self.height = height
        self.eye = (width / 2.0, height / 2.0)
        self._cos = 1.0
        self._sin = 0.0
        self._ox = 0.0
        self._oy = 0.0

    @classmethod
    def identity(cls) -> "Camera":
        """A camera that maps world coordinates straight through. For tests
        and for any draw path that wants raw coordinates."""
        cam = cls()
        cam.eye = (0.0, 0.0)
        return cam

    def update(self, x: float, y: float, angle: float, rotating: bool) -> None:
        a = angle if rotating else 0.0
        self._cos = math.cos(a)
        self._sin = math.sin(a)
        self._ox, self._oy = x, y
        if rotating:
            # Gravity is a fixed point on screen, so the lead can be too.
            self.eye = (self.width / 2.0, self.height / 2.0 - self.height * LEAD_FRACTION)
        else:
            # Dead centre: equal visibility in every direction, and nothing
            # about the framing moves when gravity turns.
            self.eye = (self.width / 2.0, self.height / 2.0)

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        dx = x - self._ox
        dy = y - self._oy
        return (self.eye[0] + dx * self._cos - dy * self._sin,
                self.eye[1] + dx * self._sin + dy * self._cos)

    def direction_to_screen(self, dx: float, dy: float) -> tuple[float, float]:
        """A direction, not a point: rotation only, no translation."""
        return (dx * self._cos - dy * self._sin, dx * self._sin + dy * self._cos)

    def to_world(self, sx: float, sy: float) -> tuple[float, float]:
        dx = sx - self.eye[0]
        dy = sy - self.eye[1]
        return (self._ox + dx * self._cos + dy * self._sin,
                self._oy - dx * self._sin + dy * self._cos)
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH= .venv/bin/pytest tests/test_camera.py -v`
Expected: all PASS. If `test_rotation_carries_gravity_onto_screen_down_at_every_step` fails, the sign is wrong — do not "fix" it by negating `angle` at the call site, fix it here once.

- [ ] **Step 5: Commit**

```bash
git add src/gravi/render/camera.py tests/test_camera.py
git commit -m "feat(render): a camera that rotates gravity onto screen-down"
```

---

## Task 5: neon draws through the camera

**Goal:** Every draw call goes through the camera, and the chamber corridor and its exit arrow are drawn.

**Files:**
- Modify: `src/gravi/render/neon.py`
- Modify: `tests/test_neon.py`

**Acceptance criteria:**
- [ ] `draw_node`, `draw_beam`, `draw_player`, `draw_trail`, `draw_glow` all take a `camera` and transform through it
- [ ] `draw_chamber(surface, chamber, camera, is_current)` draws the corridor outline; `draw_arrow(surface, chamber, camera)` draws the exit arrow spanning the full far side, with chevrons pointing along the chamber's `next_direction`
- [ ] Every existing pixel-reading test in `test_neon.py` still passes, using `Camera.identity()`
- [ ] Frame cost stays within budget: the fps/step overlay added in `b7406cb` shows ≥ 60 fps at the native window size with four chambers on screen

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_neon.py -v` → all pass

**Steps:**

- [ ] **Step 1: Update the existing tests first, minimally**

Every current call becomes the same call with `Camera.identity()` passed in. Assertions do not change — with an identity camera the pixels must land exactly where they landed in slice 1. That is the point: this task is a refactor, and the existing tests are the proof it did not change anything visible.

```python
from gravi.render.camera import Camera

IDENTITY = Camera.identity()

def test_node_ring_is_drawn_at_the_influence_radius():
    ...
    neon.draw_node(surface, node, is_active=False, camera=IDENTITY)
    ...
```

- [ ] **Step 2: Run them and watch them fail**

Run: `PYTHONPATH= .venv/bin/pytest tests/test_neon.py -v`
Expected: `TypeError: draw_node() got an unexpected keyword argument 'camera'`

- [ ] **Step 3: Thread the camera through, then add the two new draws**

Rule: a draw function transforms *points* through `camera.to_screen` and leaves *radii* alone. Radii are unchanged by rotation, which is exactly why this is cheap (there is no zoom in slice 2 — do not add one).

```python
def draw_chamber(surface, chamber, camera, is_current: bool) -> None:
    """The corridor outline. Dim for neighbours, brighter for the one you are
    in, so the seam is legible without a HUD element."""
    points = [camera.to_screen(x, y) for x, y in chamber.outline()]
    colour = _scaled(config.COLOR_CHAMBER, 1.0 if is_current else 0.45)
    pygame.draw.lines(surface, colour, True, points, 2)


def draw_arrow(surface, chamber, camera) -> None:
    """The exit arrow spans the chamber's FULL far side, so it reads as a
    threshold you cross rather than a target you aim at. Chevrons point along
    next_direction, which is where gravity will pull once you are through."""
    a, b = (camera.to_screen(*p) for p in chamber.arrow_endpoints())
    pygame.draw.line(surface, config.COLOR_ARROW, a, b, 3)
    dx, dy = camera.direction_to_screen(*chamber.next_direction)
    ...  # five chevrons spaced along the bar, as in proto/terrain-demo.html:566-584
```

Add `COLOR_CHAMBER` and `COLOR_ARROW` to `config.py` (the prototype uses a violet for the arrow — hue is charge, and the arrow is not a charge, so it must not reuse the node cyan or the repel magenta).

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH= .venv/bin/pytest tests/test_neon.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/gravi/render/neon.py src/gravi/config.py tests/test_neon.py
git commit -m "feat(render): draw through the camera, plus chamber outlines and arrows"
```

---

## Task 6: config, tunables, and the preset rename

**Goal:** `gravity_y` becomes `gravity` (it is a magnitude now), the flip and chamber knobs become live-tunable, and an old preset file loads without crashing.

**Files:**
- Modify: `src/gravi/config.py`
- Modify: `src/gravi/tuning.py`
- Modify: `presets/default.json`
- Modify: `tests/test_config.py`, `tests/test_tuning.py`

**Acceptance criteria:**
- [ ] `TUNABLES` has `gravity`, `flip_duration`, `chamber_depth`, `chamber_half_width`; no `gravity_y` remains anywhere in `src/`, `main.py` or `presets/`
- [ ] `TuningState.load` ignores unknown keys and keeps defaults for missing ones, so a stale `presets/current.json` (gitignored, and on the author's disk) loads instead of raising
- [ ] `flip_duration` range covers 0.0–0.6 s and `chamber_depth` covers 800–2600 — the two open questions of spec §9 are judged by dragging these

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_config.py tests/test_tuning.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
def test_gravity_is_a_magnitude_now():
    assert "gravity_y" not in config.TUNABLES
    assert config.TUNABLES["gravity"].default == 500.0


def test_flip_and_chamber_knobs_are_tunable():
    assert config.TUNABLES["flip_duration"].lo == 0.0
    assert config.TUNABLES["flip_duration"].hi >= 0.6
    assert config.TUNABLES["chamber_depth"].lo <= 800.0
    assert config.TUNABLES["chamber_depth"].hi >= 2600.0


def test_load_ignores_unknown_and_missing_keys(tmp_path):
    """A preset written before the rename must not crash the game."""
    path = tmp_path / "old.json"
    path.write_text('{"gravity_y": 900.0, "k_attract": 12.0}', encoding="utf-8")
    state = TuningState(default_tunables())
    assert state.load(path) is True
    assert state.values["k_attract"] == 12.0
    assert state.values["gravity"] == config.TUNABLES["gravity"].default
```

- [ ] **Step 2: Run and watch fail** → `KeyError: 'gravity'`

- [ ] **Step 3: Make the changes**

```python
    "gravity":        TunableSpec(500.0,  25.0, -2000.0, 4000.0),
    # Spec 9's two open questions live here. flip_duration is what criterion 2
    # (comfortable at rate) is judged on. chamber_depth is the flip-FREQUENCY
    # knob: at identical physics it sets how long a player spends between
    # arrows, so it is how the shipped game slows down or speeds up. 1150 gave
    # ~26 gravity swaps per minute and read as too hard; 1600 gives ~8.
    "flip_duration":  TunableSpec(0.30,   0.02,   0.0,     0.60),
    "chamber_depth":  TunableSpec(1600.0, 50.0,  800.0,  2600.0),
    "chamber_half_width": TunableSpec(460.0, 20.0, 260.0, 900.0),
```

Update `presets/default.json` to match (rename the key, add the three new ones). `presets/current.json` is gitignored, so only the checked-in default needs changing — but the load path must tolerate the stale one.

- [ ] **Step 4: Run the tests** → all PASS

- [ ] **Step 5: Commit**

```bash
git add src/gravi/config.py src/gravi/tuning.py presets/default.json tests/test_config.py tests/test_tuning.py
git commit -m "feat(config): gravity is a magnitude; flip and chamber knobs are tunable"
```

---

## Task 7: wire it in `main.py`

**Goal:** The default run is a streamed chamber corridor with a working camera toggle, and every tunable takes effect live.

**Files:**
- Modify: `main.py`

**Acceptance criteria:**
- [ ] The game boots into a generated chamber run; `R` restarts on a new seed; death respawns at the current chamber's entrance after ~0.6 s
- [ ] `C` toggles the fixed camera, and the toggle is instant with no transition
- [ ] Changing `chamber_depth` or `chamber_half_width` in the HUD regenerates the chain from the current seed and restarts the run (dimensions are structural, not per-frame)
- [ ] Changing `flip_duration` takes effect on the next flip without a restart
- [ ] The HUD shows chambers cleared, best, and distance
- [ ] The frame loop still `await asyncio.sleep(0)` every frame — the browser tab locks up otherwise

**Verify:** `PYTHONPATH= .venv/bin/python main.py` → play three chambers, toggle the camera, drag `flip_duration`, no traceback on exit

**Steps:**

- [ ] **Step 1: Replace room construction with a chain**

```python
def build_world(seed: int, tunables: dict[str, float]) -> World:
    params = ChamberParams(depth=tunables["chamber_depth"],
                           half_width=tunables["chamber_half_width"])
    return World(
        chain=ChamberChain(seed=seed, params=params),
        params=FieldParams(k_attract=tunables["k_attract"],
                           k_repel=tunables["k_repel"],
                           force_max=tunables["force_max"]),
        gravity=tunables["gravity"],
        gravity_state=GravityState(flip_duration=tunables["flip_duration"]),
        player_radius=tunables["player_radius"],
        speed_max=tunables["speed_max"],
        fall_speed_max=tunables["fall_speed_max"],
    )
```

`apply_tunables` keeps updating the live world in place for everything except the two chamber dimensions; those set a `needs_rebuild` flag that rebuilds the chain at the top of the next frame.

- [ ] **Step 2: Camera in the draw path**

```python
camera.update(world.x, world.y, world.gravity_state.angle, rotating=rotating_camera)
for index in range(max(0, world.chain.at - 1), world.chain.at + 3):
    ch = world.chain.by_index(index)
    if ch is None:
        continue
    neon.draw_chamber(screen, ch, camera, is_current=index == world.chain.at)
    neon.draw_arrow(screen, ch, camera)
```

Draw order stays: chambers and arrows, then trail, then nodes, then beam, then player, then HUD. The HUD is screen space and never goes through the camera.

- [ ] **Step 3: Keys**

`C` toggles `rotating_camera`. Default it to **rotating**, which is the mode slice 2 is judging; the prototype defaults to fixed because it exists to compare the two, and that is not what the game ships. Add the mode to the HUD status line so a playtester can never be unsure which one they are judging.

- [ ] **Step 4: Verify by playing**

Run: `PYTHONPATH= .venv/bin/python main.py`
Expected: a corridor that turns; the world swings around the player on each crossing; pressing `C` freezes the framing and the corridor visibly bends across the screen instead.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: play a streamed chamber corridor with a rotating camera"
```

---

## Task 8: keep the editor useful — `--room` lab mode

**Goal:** The slice 1 room and its editor stay reachable for authoring and tuning node fields, without a second physics path.

**Files:**
- Modify: `src/gravi/room.py` (add `room_as_chamber`)
- Modify: `main.py`
- Modify: `tests/test_editor.py` (no behaviour change; only if construction changed)
- Create: test in `tests/test_chamber.py` for the adapter

**Why:** spec §7 keeps `room.py` "for the slice 1 room and the editor, which stay useful for authoring a chamber's node field", and §9 leaves its long-term fate open. One `World` runs everything — a second simulation path would break core spec §8.1 immediately.

**Acceptance criteria:**
- [ ] `PYTHONPATH= .venv/bin/python main.py --room rooms/slice1.json` runs the slice 1 room as a single chamber with the editor keys live
- [ ] The adapter is ~10 lines and adds no new physics
- [ ] Crossing the lab chamber's arrow loops back to its entrance rather than generating a corridor

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/ -v` → all pass; then `PYTHONPATH= .venv/bin/python main.py --room rooms/slice1.json` → the slice 1 room, editable

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_a_room_becomes_one_chamber_with_the_same_nodes():
    room = Room(spawn=(100.0, 60.0), nodes=[Node(400.0, 300.0, 200.0, 16.0)],
                width=1280.0, height=720.0)
    ch = room_as_chamber(room)
    assert [(n.x, n.y) for n in ch.nodes] == [(400.0, 300.0)]
    assert ch.params.depth == pytest.approx(720.0)
```

- [ ] **Step 2: Run and watch it fail** → `ImportError: cannot import name 'room_as_chamber'`

- [ ] **Step 3: Write the adapter and the `--room` branch**

The chamber's frame is the room's: entry at the top-centre of the room, direction `(0, 1)`, depth `room.height`, half-width `room.width / 2`.

- [ ] **Step 4: Run the suite and the lab mode** → pass, and the room is editable

- [ ] **Step 5: Commit**

```bash
git add src/gravi/room.py main.py tests/test_chamber.py
git commit -m "feat: run a hand-authored room as a single chamber in lab mode"
```

---

## Task 9: browser build, playtest, verdict

**Goal:** Answer slice 2's three criteria by playing it, in the browser as well as natively, and write the verdict down.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Create: `docs/superpowers/runbooks/YYYY-MM-DD-slice-2-rotation-verdict.md`
- Modify: `docs/superpowers/specs/2026-08-13-gravi-slice-2-gravity-and-camera-design.md` (status → approved, plus any amendment the playtest forces)
- Modify: `README.md` (status line), `presets/default.json` (winning values)

**Acceptance criteria:**
- [ ] `PYTHONPATH= .venv/bin/pytest tests/ -v` passes in full, with the count recorded in the runbook
- [ ] `.venv/bin/pygbag --build main.py` succeeds and the built game is **played in a browser** for at least five minutes — not merely booted (slice 1's verdict recorded this exact gap and it is still open)
- [ ] Criterion 1 (no re-orientation beat), criterion 2 (five minutes at the fastest flip rate we would ship, no motion sickness) and criterion 3 (a bad crossing is your fault) each get an explicit yes/no with the reasoning
- [ ] Final `flip_duration` and `chamber_depth` are recorded as winning values in `presets/default.json`, closing two of spec §9's open questions
- [ ] The fixed-camera mode is confirmed to exist and be usable — it is explicitly **not** a gate on being as pleasant as the rotating one
- [ ] The runbook records coverage gaps plainly, in the style of `2026-08-11-slice-1-feel-verdict.md`

**Verify:** the runbook exists, names the build SHA, and states PROCEED or STOP

**Steps:**

- [ ] **Step 1: Full suite, recorded**

Run: `PYTHONPATH= .venv/bin/pytest tests/ -v 2>&1 | tail -5`
Capture the count for the runbook.

- [ ] **Step 2: Build and serve the browser version**

Run: `PYTHONPATH= .venv/bin/pygbag --build main.py` then serve `build/web` and open it. `docs/web-build.md` has the working recipe.

- [ ] **Step 3: Play both modes, natively and in the browser**

Sweep `flip_duration` and `chamber_depth` while playing. The pace slider from the prototype is deliberately **not** ported: if the game only reads well in slow motion, the honest answer is deeper chambers or lower gravity, not slow motion.

- [ ] **Step 4: Write the verdict**

Mirror the slice 1 runbook: decision, criteria table, what changed during the playtest, winning values, supporting evidence, coverage gaps. If a criterion fails, say so and say what it costs — spec §3.3 already anticipates criterion 2 capping an escalation axis, and that is a finding, not a failure of the slice.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/runbooks/ docs/superpowers/specs/ README.md presets/default.json
git commit -m "docs(slice2): rotation verdict and the winning flip values"
```

---

## When you are done

Report back to the coordinating session with: the verdict, the final `flip_duration` and `chamber_depth`, the test count, and **whether the force-law constants moved**. That last one matters beyond this session: sessions S6 and S7 cannot bake a validated chamber library until the physics constants are frozen, because retuning the force law invalidates every difficulty measurement (core spec §4.4).
