# Gravi Slice 1 — Feel Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a playable prototype that answers the one question the whole Gravi design rests on — does whipping around a solid-core node under a linear central force feel good — with live tuning, in-session room editing, and a browser build.

**Architecture:** A pure, pygame-free simulation core (`field.py` for the force law, `sim.py` for a deterministic fixed-step integrator, `room.py` for level data) with a pygame-ce presentation layer on top (`render/`, `editor.py`) wired together by an async `main.py`. No physics engine: the player is a point mass under gravity plus at most one central force, so a hand-written semi-implicit Euler integrator is simpler, exactly deterministic, far faster for the offline validator in later slices, and — decisively — it runs in the browser, which pymunk does not.

**Tech Stack:** Python 3.12, pygame-ce 2.5+, pytest 8+, pygbag (browser packaging). No pymunk, no numpy — every runtime dependency must survive compilation to WebAssembly.

---

## Stack decisions locked by this plan

These follow from the spec plus the web-deployment requirement added on 2026-08-11. They are recorded here because they change §8 of the spec.

| Decision | Choice | Reason |
|---|---|---|
| Physics engine | **None.** Hand-written fixed-step integrator | Player is a point mass with one central force and a circle-overlap death check. Pymunk is a C/CFFI extension with no working browser story, and it would block the whole web target. Also makes determinism exact and headless rollouts (spec §4.2) cheap. |
| Web packaging | **pygbag** | Packages pygame-ce to WebAssembly. Requires an `async` main loop and `main.py` at the packaged root — both cheap now, painful to retrofit. |
| Dependencies | pygame-ce only at runtime | Every dependency is a browser-compatibility risk. numpy is available under pygbag but slice 1 does not need it. |
| Integrator | Semi-implicit (symplectic) Euler at 240 Hz | Symplectic integrators do not pump energy on oscillators, which a linear central force is. Orbits stay stable instead of spiralling. |
| Player mass | Fixed at 1.0 | Force equals acceleration, so there is one fewer number to tune. Mass is not a mechanic in Gravi. |
| Glow rendering | Pre-baked radial sprites blitted with `BLEND_ADD` | Per-frame gradient generation is the obvious WASM performance cliff. Bake once, cache by (colour, radius). |

**A property worth knowing while tuning:** under a linear central force the orbital period is `2π/√k_attract` and is *independent of orbit size*. Every orbit takes the same time regardless of how tight it is. Expect that to feel unusual and good; it means orbit timing is learnable in a way inverse-square orbits never are.

---

## File structure

| Path | Responsibility | Imports pygame? |
|---|---|---|
| `main.py` | Async entry point; the frame loop; wires input → sim → render | yes |
| `src/gravi/config.py` | Default tunable values, window constants, palette | no |
| `src/gravi/field.py` | The force law. Charge enum, FieldParams, Node, `charge_force()` | **never** |
| `src/gravi/sim.py` | `World`: player state, fixed-step integration, active-node selection, death | **never** |
| `src/gravi/room.py` | `Room` dataclass; JSON load/save | **never** |
| `src/gravi/editor.py` | Mouse-driven node editing state machine (pure logic, takes plain values) | no |
| `src/gravi/render/neon.py` | Glow sprite cache; draw node, beam, player, trail | yes |
| `src/gravi/render/hud.py` | Live tuning overlay: parameter list, selection, adjustment, text | yes |
| `src/gravi/render/trail.py` | Trail point buffer (pure deque wrapper) | no |
| `rooms/slice1.json` | The hand-placed starting room | — |
| `presets/default.json` | Starting tuning values | — |
| `tests/` | pytest suite | test-dependent |

The pygame-free boundary is the whole point: `field.py`, `sim.py`, and `room.py` are what the offline validator and trainer will import in later slices, and spec §8.1 makes sharing that code non-negotiable.

---

### Task 1: Repo skeleton and async frame loop

**Goal:** A `pip install -e .[dev]` package with a pytest suite and an async pygame window that opens, clears to the neon background, and closes cleanly.

**Files:**
- Create: `pyproject.toml`
- Create: `main.py`
- Create: `src/gravi/__init__.py`
- Create: `src/gravi/config.py`
- Create: `tests/test_config.py`

**Acceptance Criteria:**
- [ ] `pip install -e .[dev]` succeeds
- [ ] `pytest -q` runs and passes
- [ ] `python main.py` opens a 1280×720 window filled with the background colour and closes on window-close or Escape
- [ ] `main()` is an `async def` driven by `asyncio.run`, with `await asyncio.sleep(0)` once per frame
- [ ] `src/gravi/__init__.py` imports nothing (the purity test in Task 4 imports the package)

**Verify:** `pytest -q` → `2 passed`, and `python main.py` opens a window that closes on Escape

**Steps:**

- [ ] **Step 0: Write `src/gravi/__init__.py`**

Must stay import-free: `tests/test_purity.py` (Task 4) asserts that importing the simulation core never pulls in pygame, and a package `__init__` that imports the renderer would defeat it.

```python
"""Gravi — an endless polarity game.

Deliberately empty of imports: gravi.field / gravi.sim / gravi.room are shared
with the offline validator and must stay pygame-free (spec section 8.1).
"""
```

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "gravi"
version = "0.1.0"
description = "An endless polarity game — you never jump, you push and pull against the world"
requires-python = ">=3.12"
dependencies = [
    "pygame-ce>=2.5",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pygbag>=0.9",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

- [ ] **Step 2: Write `src/gravi/config.py`**

```python
"""Default tunable values for Gravi. Everything in TUNABLES is live-adjustable
in-game via the HUD overlay (see render/hud.py); the values here are only the
starting point a session begins from."""

from __future__ import annotations

from typing import NamedTuple

# Display
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
TARGET_FPS = 60

# Simulation. 240 Hz because orbits under a central force integrate more
# accurately at higher rates, and a point mass is cheap enough to afford it.
PHYS_HZ = 240
PHYS_DT = 1.0 / PHYS_HZ
MAX_STEPS_PER_FRAME = 12  # avoid a spiral of death after a long stall

# Palette — near-black field, everything else is emitted light.
COLOR_BG = (5, 6, 11)
COLOR_NODE = (80, 240, 255)      # cyan: an anchor you can use
COLOR_CORE = (235, 255, 255)     # the solid, lethal centre
COLOR_PLAYER = (255, 240, 120)
COLOR_BEAM_ATTRACT = (80, 240, 255)
COLOR_BEAM_REPEL = (255, 120, 200)
COLOR_TRAIL = (120, 180, 255)
COLOR_HUD = (200, 220, 235)

# Trail
TRAIL_MAX_POINTS = 900  # ~15 s at 60 fps


class TunableSpec(NamedTuple):
    default: float
    step: float
    lo: float
    hi: float


# Live-tunable simulation values. Name -> (default, step, min, max).
# The HUD iterates this dict in insertion order.
#
# TUNABLES itself must never be mutated directly — it is the process-wide
# set of starting points. Callers that need to adjust values in place (e.g.
# the HUD overlay in render/hud.py) take a per-session copy via
# default_tunables() and mutate that instead.
TUNABLES: dict[str, TunableSpec] = {
    # Orbital period is 2*pi/sqrt(k_attract) and is independent of orbit size.
    "k_attract":     TunableSpec(8.0,    0.5,   0.5,  60.0),
    "k_repel":       TunableSpec(12.0,   0.5,   0.5, 120.0),
    "force_max":     TunableSpec(4000.0, 100.0, 100.0, 20000.0),
    "gravity_y":     TunableSpec(900.0,  25.0, -2000.0, 4000.0),
    "speed_max":     TunableSpec(2000.0, 50.0,  100.0, 8000.0),
    "player_radius": TunableSpec(9.0,    1.0,    2.0,   40.0),
}


def default_tunables() -> dict[str, float]:
    """A fresh mutable name -> value mapping seeded from TUNABLES defaults."""
    return {name: spec.default for name, spec in TUNABLES.items()}
```

- [ ] **Step 3: Write the failing test `tests/test_config.py`**

```python
from gravi import config


def test_every_tunable_default_is_inside_its_own_bounds():
    for name, (default, step, lo, hi) in config.TUNABLES.items():
        assert lo <= default <= hi, f"{name} default {default} outside [{lo}, {hi}]"
        assert step > 0, f"{name} step must be positive"


def test_default_tunables_returns_a_fresh_dict():
    a = config.default_tunables()
    b = config.default_tunables()
    a["k_attract"] = 999.0
    assert b["k_attract"] == config.TUNABLES["k_attract"][0]
```

- [ ] **Step 4: Run the test**

Run: `pytest -q`
Expected: PASS (2 passed) — this test guards the config table rather than driving new code.

- [ ] **Step 5: Write `main.py`**

```python
"""Gravi entry point.

The loop is async because pygbag (the browser packager) drives the frame loop
through the JS event loop: without `await asyncio.sleep(0)` each frame the
browser tab locks up. Costs nothing natively, impossible to retrofit cheaply.
"""

from __future__ import annotations

import asyncio

import pygame

from gravi import config


async def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption("Gravi")
    clock = pygame.time.Clock()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        screen.fill(config.COLOR_BG)
        pygame.display.flip()

        clock.tick(config.TARGET_FPS)
        await asyncio.sleep(0)  # REQUIRED for pygbag; do not remove

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Install and verify by hand**

Run:
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]
pytest -q
python main.py
```
Expected: `2 passed`; a 1280×720 near-black window opens and closes on Escape.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml main.py src/gravi/__init__.py src/gravi/config.py tests/test_config.py
git commit -m "feat: repo skeleton, tunables table, async pygame loop"
```

---

### Task 2: Prove the browser deployment path

**Goal:** Confirm the blank window from Task 1 builds with pygbag and runs in a real browser, before any game code is written on top of the stack.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

This task is deliberately second. If pygbag cannot package this app, the stack decision changes and every later task changes with it — that must be discovered on day one, not after the prototype exists.

**Files:**
- Create: `docs/web-build.md`
- Modify: `.gitignore` (add `build/`)

**Acceptance Criteria:**
- [ ] `pygbag --build .` completes without error and produces `build/web/index.html` plus a `.apk` payload
- [ ] `pygbag .` serves the app and `http://localhost:8000` renders the near-black 1280×720 canvas in a browser
- [ ] The browser console shows no uncaught Python traceback
- [ ] `docs/web-build.md` records the exact build command, the serve command, and the pygbag version that worked

**Verify:** `pygbag --build . && ls build/web/index.html` → path printed; then `pygbag .` and load `http://localhost:8000` in a browser and confirm a near-black canvas

**Steps:**

- [ ] **Step 1: Add the build output to `.gitignore`**

```
build/
```

- [ ] **Step 2: Build**

Run: `pygbag --build .`
Expected: pygbag downloads its WASM runtime on first use, then exits 0. `build/web/` contains `index.html`.

If it fails because it cannot find an entry point, confirm `main.py` is at the repo root — pygbag packages the directory it is pointed at and requires `main.py` there.

- [ ] **Step 3: Serve and open a browser**

Run: `pygbag .`
Then open `http://localhost:8000` and watch the canvas.
Expected: a loading bar, then a near-black 1280×720 canvas. Open the browser devtools console and confirm no Python traceback.

- [ ] **Step 4: Record what worked in `docs/web-build.md`**

```markdown
# Web build

Gravi targets the browser via [pygbag](https://pypi.org/project/pygbag/), which
packages a pygame-ce app to WebAssembly.

    pygbag --build .        # produce build/web/
    pygbag .                # build + serve on http://localhost:8000

Verified working with pygbag <VERSION FROM `pip show pygbag`> on <DATE>.

## Constraints this imposes

- `main.py` must stay at the repo root — pygbag packages the directory it is
  given and looks for `main.py` there.
- The frame loop must `await asyncio.sleep(0)` every frame or the browser tab
  locks up.
- Runtime dependencies must be pure Python or shipped by the pygbag runtime.
  This is why Gravi has no pymunk and no physics engine (see the slice 1 plan).
- Writing to disk (tuning presets, edited rooms) works natively but not in the
  browser build; save paths must fail soft rather than raise.
```

Replace `<VERSION FROM ...>` and `<DATE>` with the real values before committing.

- [ ] **Step 5: Commit**

```bash
git add docs/web-build.md .gitignore
git commit -m "build: verify pygbag browser packaging on the blank loop"
```

---

### Task 3: The force law

**Goal:** `field.py` — a pure module holding attract, repel, clamping, and the node definition, with tests that pin every branch of the maths.

**Files:**
- Create: `src/gravi/field.py`
- Create: `tests/test_field.py`

**Acceptance Criteria:**
- [ ] Attract returns a force pointing at the node centre with magnitude `k_attract * r`
- [ ] Repel returns a force pointing away with magnitude `k_repel * (R - r)`
- [ ] Both return `(0.0, 0.0)` outside the influence radius and when the charge is neutral
- [ ] Both are clamped to `force_max`
- [ ] Attract at exactly the node centre returns `(0.0, 0.0)` rather than dividing by zero
- [ ] `field.py` contains no pygame import

**Verify:** `pytest tests/test_field.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests `tests/test_field.py`**

```python
import math

import pytest

from gravi.field import Charge, FieldParams, Node, charge_force

PARAMS = FieldParams(k_attract=8.0, k_repel=12.0, force_max=1e9)
NODE = Node(x=100.0, y=100.0, radius=200.0, core_radius=18.0)


def test_attract_points_at_the_node_with_magnitude_k_times_r():
    # player 50px to the left of the node
    fx, fy = charge_force(50.0, 100.0, NODE, Charge.ATTRACT, PARAMS)
    assert fy == pytest.approx(0.0)
    assert fx == pytest.approx(8.0 * 50.0)  # positive = toward the node


def test_repel_points_away_with_magnitude_k_times_radius_minus_r():
    fx, fy = charge_force(50.0, 100.0, NODE, Charge.REPEL, PARAMS)
    assert fy == pytest.approx(0.0)
    assert fx == pytest.approx(-12.0 * (200.0 - 50.0))  # negative = away


def test_attract_is_strongest_at_the_rim_and_repel_at_the_core():
    near = charge_force(90.0, 100.0, NODE, Charge.ATTRACT, PARAMS)
    far = charge_force(-90.0, 100.0, NODE, Charge.ATTRACT, PARAMS)
    assert math.hypot(*far) > math.hypot(*near)

    near_r = charge_force(90.0, 100.0, NODE, Charge.REPEL, PARAMS)
    far_r = charge_force(-90.0, 100.0, NODE, Charge.REPEL, PARAMS)
    assert math.hypot(*near_r) > math.hypot(*far_r)


def test_no_force_outside_the_influence_radius():
    assert charge_force(1000.0, 100.0, NODE, Charge.ATTRACT, PARAMS) == (0.0, 0.0)
    assert charge_force(1000.0, 100.0, NODE, Charge.REPEL, PARAMS) == (0.0, 0.0)


def test_no_force_when_neutral():
    assert charge_force(50.0, 100.0, NODE, Charge.NEUTRAL, PARAMS) == (0.0, 0.0)


def test_force_is_clamped_to_force_max():
    clamped = FieldParams(k_attract=8.0, k_repel=12.0, force_max=100.0)
    fx, fy = charge_force(50.0, 100.0, NODE, Charge.ATTRACT, clamped)
    assert math.hypot(fx, fy) == pytest.approx(100.0)


def test_dead_centre_does_not_divide_by_zero():
    assert charge_force(100.0, 100.0, NODE, Charge.ATTRACT, PARAMS) == (0.0, 0.0)
    assert charge_force(100.0, 100.0, NODE, Charge.REPEL, PARAMS) == (0.0, 0.0)


def test_diagonal_force_is_aligned_with_the_offset():
    node = Node(x=0.0, y=0.0, radius=500.0, core_radius=10.0)
    fx, fy = charge_force(-30.0, -40.0, node, Charge.ATTRACT, PARAMS)
    # offset is (30, 40), length 50 -> unit (0.6, 0.8), magnitude 8 * 50 = 400
    assert fx == pytest.approx(400.0 * 0.6)
    assert fy == pytest.approx(400.0 * 0.8)
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_field.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gravi.field'`

- [ ] **Step 3: Write `src/gravi/field.py`**

```python
"""The force law. THE single source of truth for Gravi's physics.

This module is imported by the game, by the offline chamber validator, and by
the trainer. It must never import pygame, the scene layer, or the renderer —
if the validator ever simulates physics that differ from the game, every
difficulty measurement it produces is fiction (see spec section 8.1).

Attract is a LINEAR central force, F = k*r toward the centre, not inverse
square. Three reasons, in priority order:
  1. No singularity at r = 0, so close passes are well behaved.
  2. Bounded orbits close on themselves, so a grab produces a repeating
     ellipse rather than a spiral to fight. Orbital period is 2*pi/sqrt(k)
     and does not depend on orbit size.
  3. Force grows with distance, which reads exactly like the stretched beam
     the player is looking at.

Repel is the mirror in range profile: strongest at contact, fading to zero at
the rim. Attract is a long-range whip; repel is a close-range kick.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

Vec = tuple[float, float]

_EPSILON = 1e-9


class Charge(IntEnum):
    """The player's three states. There is no fourth input in Gravi."""

    REPEL = -1
    NEUTRAL = 0
    ATTRACT = 1


@dataclass(frozen=True)
class FieldParams:
    """Live-tunable force constants. k units are 1/s^2 (force per unit mass)."""

    k_attract: float
    k_repel: float
    force_max: float


@dataclass(frozen=True)
class Node:
    """A charged anchor. `radius` is the influence radius the glow ring draws;
    `core_radius` is the solid, lethal centre."""

    x: float
    y: float
    radius: float
    core_radius: float


def charge_force(
    px: float, py: float, node: Node, charge: Charge, params: FieldParams
) -> Vec:
    """Force on a unit-mass player at (px, py) from `node` under `charge`.

    Returns (0.0, 0.0) when neutral, outside the influence radius, or exactly
    at the node centre.
    """
    if charge is Charge.NEUTRAL:
        return (0.0, 0.0)

    dx = node.x - px
    dy = node.y - py
    r = math.hypot(dx, dy)

    if r > node.radius or r < _EPSILON:
        return (0.0, 0.0)

    if charge is Charge.ATTRACT:
        magnitude = params.k_attract * r
        sign = 1.0
    else:
        magnitude = params.k_repel * (node.radius - r)
        sign = -1.0

    magnitude = min(magnitude, params.force_max)
    ux = dx / r
    uy = dy / r
    return (sign * magnitude * ux, sign * magnitude * uy)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_field.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gravi/field.py tests/test_field.py
git commit -m "feat: linear-central-force field law with attract/repel and clamping"
```

---

### Task 4: Deterministic simulation core

**Goal:** `sim.py` — a `World` that integrates the player under gravity plus the active node's force at a fixed timestep, selects the active node, and detects death, with a test proving two identical runs produce byte-identical traces.

**Files:**
- Create: `src/gravi/room.py`
- Create: `src/gravi/sim.py`
- Create: `tests/test_sim.py`
- Create: `tests/test_purity.py`

**Acceptance Criteria:**
- [ ] `World.step()` advances one fixed timestep using semi-implicit Euler
- [ ] The active node is the nearest node whose influence radius contains the player, ties broken by lowest index; `None` when outside all radii
- [ ] Only the active node contributes force
- [ ] Player dies on contact with a node core, and when leaving the room bounds
- [ ] Two `World`s stepped with the same charge sequence produce identical position traces under exact `==`
- [ ] A stable orbit stays stable: attracting with tangential velocity keeps the player within a bounded distance band for 10 simulated seconds
- [ ] Importing `gravi.sim` does not import pygame

**Verify:** `pytest tests/test_sim.py tests/test_purity.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests `tests/test_sim.py`**

```python
import math

import pytest

from gravi.field import Charge, FieldParams, Node
from gravi.room import Room
from gravi.sim import World

PARAMS = FieldParams(k_attract=8.0, k_repel=12.0, force_max=1e9)


def make_world(gravity_y=0.0, spawn=(300.0, 400.0), nodes=None,
               width=1280.0, height=720.0, speed_max=1e9):
    room = Room(
        spawn=spawn,
        nodes=nodes if nodes is not None else [Node(400.0, 400.0, 250.0, 18.0)],
        width=width,
        height=height,
    )
    return World(room=room, params=PARAMS, gravity_y=gravity_y,
                 player_radius=9.0, speed_max=speed_max)


def test_gravity_accelerates_the_player_downward():
    # Tall room so the out-of-bounds death check does not halt the fall before
    # a full second has elapsed.
    w = make_world(gravity_y=1000.0, nodes=[], height=1e6)
    for _ in range(240):  # one second at 240 Hz
        w.step(Charge.NEUTRAL)
    assert w.vy == pytest.approx(1000.0, rel=1e-6)


def test_active_node_is_the_nearest_containing_node():
    near = Node(310.0, 400.0, 100.0, 10.0)
    far = Node(360.0, 400.0, 400.0, 10.0)
    w = make_world(nodes=[far, near])
    assert w.active_node() is near


def test_active_node_is_none_outside_every_radius():
    w = make_world(nodes=[Node(1000.0, 1000.0, 50.0, 10.0)])
    assert w.active_node() is None


def test_ties_break_on_lowest_index():
    a = Node(300.0, 350.0, 200.0, 10.0)
    b = Node(300.0, 450.0, 200.0, 10.0)  # same distance from spawn (300, 400)
    w = make_world(nodes=[a, b])
    assert w.active_node() is a


def test_only_the_active_node_applies_force():
    # Two overlapping nodes pulling opposite ways. If both applied force they
    # would partially cancel; only the nearer one may contribute.
    near = Node(400.0, 400.0, 400.0, 10.0)   # 100px right of spawn
    far = Node(100.0, 400.0, 400.0, 10.0)    # 200px left of spawn
    w = make_world(nodes=[far, near])
    assert w.active_node() is near
    w.step(Charge.ATTRACT)
    expected_ax = 8.0 * 100.0  # k_attract * r toward the near node, i.e. +x
    assert w.vx == pytest.approx(expected_ax * w.dt, rel=1e-9)
    assert w.vx > 0.0


def test_player_dies_on_core_contact():
    w = make_world(spawn=(400.0, 400.0 - 30.0),
                   nodes=[Node(400.0, 400.0, 250.0, 18.0)])
    assert not w.dead
    for _ in range(240 * 3):
        w.step(Charge.ATTRACT)
        if w.dead:
            break
    assert w.dead


def test_player_dies_leaving_room_bounds():
    w = make_world(gravity_y=2000.0, nodes=[])
    for _ in range(240 * 5):
        w.step(Charge.NEUTRAL)
        if w.dead:
            break
    assert w.dead


def test_reset_restores_spawn_state():
    w = make_world(gravity_y=1000.0, nodes=[])
    for _ in range(100):
        w.step(Charge.NEUTRAL)
    w.reset()
    assert (w.x, w.y) == w.room.spawn
    assert (w.vx, w.vy) == (0.0, 0.0)
    assert not w.dead


def test_simulation_is_deterministic():
    """Also stands in for the spec's replay-fidelity requirement in slice 1:
    the same input sequence replays to the same outcome. A full input recorder
    arrives with ghosts and the path map in later slices."""
    charges = [Charge.ATTRACT] * 300 + [Charge.NEUTRAL] * 120 + [Charge.REPEL] * 180

    def trace():
        w = make_world(gravity_y=900.0, height=1e6)
        out = []
        for c in charges:
            w.step(c)
            out.append((w.x, w.y, w.vx, w.vy))
        return out

    assert trace() == trace()  # exact equality, not approx


def test_orbit_stays_bounded_for_ten_seconds():
    node = Node(400.0, 400.0, 400.0, 5.0)
    w = make_world(nodes=[node])
    # Circular orbit for F = k*r needs v = r*sqrt(k); r = 100 here.
    w.vy = 100.0 * math.sqrt(8.0)
    distances = []
    for _ in range(240 * 10):
        w.step(Charge.ATTRACT)
        assert not w.dead
        distances.append(math.hypot(w.x - node.x, w.y - node.y))
    assert min(distances) > 90.0
    assert max(distances) < 110.0


def test_speed_is_clamped_to_speed_max():
    w = make_world(gravity_y=10000.0, nodes=[], height=1e6, speed_max=50.0)
    for _ in range(240):
        w.step(Charge.NEUTRAL)
    assert math.hypot(w.vx, w.vy) <= 50.0 + 1e-9
```

- [ ] **Step 2: Write the failing purity test `tests/test_purity.py`**

```python
"""Spec section 8.1: the simulation core is shared with the offline validator
and the trainer, so it must not drag in pygame. A subprocess is used because
importing pygame anywhere else in the test session would mask the problem."""

import subprocess
import sys


def test_sim_core_does_not_import_pygame():
    code = (
        "import gravi.sim, gravi.field, gravi.room, sys; "
        "assert 'pygame' not in sys.modules, sorted(m for m in sys.modules if 'pygame' in m)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 3: Run both to confirm they fail**

Run: `pytest tests/test_sim.py tests/test_purity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gravi.room'`

- [ ] **Step 4: Write `src/gravi/room.py`**

```python
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
```

- [ ] **Step 5: Write `src/gravi/sim.py`**

```python
"""The simulation core: a point mass under gravity plus one central force.

No physics engine. The entire dynamic state is six floats and the only contact
test is circle-vs-circle, so a hand-written symplectic integrator is simpler,
exactly deterministic, fast enough for the offline validator to run thousands
of headless rollouts, and — unlike pymunk — it runs in the browser.

Semi-implicit (symplectic) Euler is used deliberately: a linear central force
is a harmonic oscillator, and symplectic integrators do not pump energy into
oscillators the way explicit Euler does, so orbits stay stable instead of
spiralling outward.

Never import pygame here (see tests/test_purity.py).
"""

from __future__ import annotations

import math

from .config import PHYS_DT
from .field import Charge, FieldParams, Node, charge_force
from .room import Room


class World:
    """Mutable simulation state for one attempt at a room."""

    def __init__(
        self,
        room: Room,
        params: FieldParams,
        gravity_y: float,
        player_radius: float,
        speed_max: float,
        dt: float = PHYS_DT,
    ) -> None:
        self.room = room
        self.params = params
        self.gravity_y = gravity_y
        self.player_radius = player_radius
        self.speed_max = speed_max
        self.dt = dt

        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.dead = False
        self.elapsed = 0.0
        self.reset()

    def reset(self) -> None:
        self.x, self.y = self.room.spawn
        self.vx = 0.0
        self.vy = 0.0
        self.dead = False
        self.elapsed = 0.0

    def active_node(self) -> Node | None:
        """Nearest node whose influence radius contains the player. Ties break
        on lowest index so the choice is deterministic. Overlapping fields
        producing a net force is a deliberate late-game escalation (spec 3.6),
        not a slice 1 feature."""
        best: Node | None = None
        best_distance = math.inf
        for node in self.room.nodes:
            distance = math.hypot(node.x - self.x, node.y - self.y)
            if distance <= node.radius and distance < best_distance:
                best = node
                best_distance = distance
        return best

    def step(self, charge: Charge) -> None:
        """Advance one fixed timestep. No-op once dead."""
        if self.dead:
            return

        ax = 0.0
        ay = self.gravity_y  # mass is fixed at 1.0, so force == acceleration

        node = self.active_node()
        if node is not None:
            fx, fy = charge_force(self.x, self.y, node, charge, self.params)
            ax += fx
            ay += fy

        self.vx += ax * self.dt
        self.vy += ay * self.dt

        speed = math.hypot(self.vx, self.vy)
        if speed > self.speed_max and speed > 0.0:
            scale = self.speed_max / speed
            self.vx *= scale
            self.vy *= scale

        self.x += self.vx * self.dt
        self.y += self.vy * self.dt
        self.elapsed += self.dt

        self._check_death()

    def _check_death(self) -> None:
        for node in self.room.nodes:
            lethal = node.core_radius + self.player_radius
            if math.hypot(node.x - self.x, node.y - self.y) <= lethal:
                self.dead = True
                return

        margin = 200.0  # let the player leave the frame briefly and recover
        if not (-margin <= self.x <= self.room.width + margin):
            self.dead = True
        elif not (-margin <= self.y <= self.room.height + margin):
            self.dead = True


def charge_from_input(attract_held: bool, repel_held: bool) -> Charge:
    """Map the two inputs to a charge. Holding both is neutral — pressing
    everything must never be the strongest option."""
    if attract_held and not repel_held:
        return Charge.ATTRACT
    if repel_held and not attract_held:
        return Charge.REPEL
    return Charge.NEUTRAL
```

- [ ] **Step 6: Add the input-mapping test to `tests/test_sim.py`**

```python
from gravi.sim import charge_from_input


def test_charge_from_input_maps_all_four_combinations():
    assert charge_from_input(True, False) is Charge.ATTRACT
    assert charge_from_input(False, True) is Charge.REPEL
    assert charge_from_input(False, False) is Charge.NEUTRAL
    assert charge_from_input(True, True) is Charge.NEUTRAL
```

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_sim.py tests/test_purity.py -v`
Expected: PASS (13 passed)

- [ ] **Step 8: Commit**

```bash
git add src/gravi/room.py src/gravi/sim.py tests/test_sim.py tests/test_purity.py
git commit -m "feat: deterministic point-mass simulation core with active-node selection"
```

---

### Task 5: Neon rendering — nodes, beam, player, trail

**Goal:** Draw the world as emitted light: pre-baked additive glow sprites, an influence-radius ring, a lethal core, a beam whose thickness tracks force magnitude, and a fading motion trail.

**Files:**
- Create: `src/gravi/render/__init__.py`
- Create: `src/gravi/render/trail.py`
- Create: `src/gravi/render/neon.py`
- Create: `tests/test_trail.py`

**Acceptance Criteria:**
- [ ] Glow sprites are baked once per (colour, radius) and cached; no per-frame gradient generation
- [ ] A node draws as a dim influence ring at `radius` plus a bright core disc at `core_radius`
- [ ] The beam is drawn only when a node is active and the charge is not neutral, tinted cyan for attract and pink for repel, with width scaled by force magnitude
- [ ] The trail keeps at most `TRAIL_MAX_POINTS` points and fades from tail to head
- [ ] `trail.py` has no pygame import (it is pure state) and is unit-tested

**Verify:** `pytest tests/test_trail.py -v` → all pass; then `python main.py` after Task 6 shows glowing nodes and a trail

**Steps:**

- [ ] **Step 1: Write the failing test `tests/test_trail.py`**

```python
from gravi.render.trail import Trail


def test_trail_records_points_in_order():
    t = Trail(max_points=5)
    t.add(1.0, 2.0)
    t.add(3.0, 4.0)
    assert list(t.points()) == [(1.0, 2.0), (3.0, 4.0)]


def test_trail_drops_the_oldest_point_past_the_cap():
    t = Trail(max_points=3)
    for i in range(5):
        t.add(float(i), 0.0)
    assert list(t.points()) == [(2.0, 0.0), (3.0, 0.0), (4.0, 0.0)]


def test_clear_empties_the_trail():
    t = Trail(max_points=3)
    t.add(1.0, 1.0)
    t.clear()
    assert list(t.points()) == []
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_trail.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gravi.render'`

- [ ] **Step 3: Write `src/gravi/render/__init__.py`**

```python
"""Presentation layer. Everything in this package may import pygame; nothing
in gravi.field, gravi.sim, or gravi.room may import anything from here."""
```

- [ ] **Step 4: Write `src/gravi/render/trail.py`**

```python
"""The player's recent path. Pure state so it can be unit-tested without a
display, and so the slice 6 path map can reuse it unchanged."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable


class Trail:
    def __init__(self, max_points: int) -> None:
        self._points: deque[tuple[float, float]] = deque(maxlen=max_points)

    def add(self, x: float, y: float) -> None:
        self._points.append((x, y))

    def points(self) -> Iterable[tuple[float, float]]:
        return tuple(self._points)

    def clear(self) -> None:
        self._points.clear()

    def __len__(self) -> int:
        return len(self._points)
```

- [ ] **Step 5: Run the trail tests**

Run: `pytest tests/test_trail.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Write `src/gravi/render/neon.py`**

```python
"""Neon drawing primitives.

Light is the ruleset in Gravi (spec section 7): hue is charge, the glow ring
IS the influence radius, and beam intensity IS force magnitude. There is no
separate HUD for any of that.

Performance note that matters for the browser build: glow is expensive if you
generate gradients every frame. Every glow here is baked once into a surface,
cached by (colour, radius), and blitted with BLEND_ADD.
"""

from __future__ import annotations

import math

import pygame

from .. import config
from ..field import Charge

_glow_cache: dict[tuple[tuple[int, int, int], int], pygame.Surface] = {}
_ring_cache: dict[tuple[int, int], pygame.Surface] = {}
_scratch: pygame.Surface | None = None


def _scratch_layer(size: tuple[int, int]) -> pygame.Surface:
    """One reusable full-screen alpha layer, cleared per use. Allocating a
    1280x720 SRCALPHA surface twice a frame is the obvious WASM cliff.

    Callers MUST blit their result before anyone else calls this — it is a
    single shared buffer, not a pool.
    """
    global _scratch
    if _scratch is None or _scratch.get_size() != size:
        _scratch = pygame.Surface(size, pygame.SRCALPHA)
    _scratch.fill((0, 0, 0, 0))
    return _scratch


def _glow_sprite(color: tuple[int, int, int], radius: int) -> pygame.Surface:
    """A radial falloff disc, baked once. Blit with BLEND_ADD."""
    key = (color, radius)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached

    size = radius * 2
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    for step in range(radius, 0, -1):
        # Quadratic falloff reads closer to real light than a linear ramp.
        t = step / radius
        alpha = int(255 * (1.0 - t) ** 2)
        if alpha <= 0:
            continue
        pygame.draw.circle(surface, (*color, alpha), (radius, radius), step)
    _glow_cache[key] = surface
    return surface


def draw_glow(surface: pygame.Surface, x: float, y: float,
              color: tuple[int, int, int], radius: int) -> None:
    sprite = _glow_sprite(color, radius)
    surface.blit(sprite, (int(x) - radius, int(y) - radius),
                 special_flags=pygame.BLEND_ADD)


def _ring_sprite(radius: int, alpha: int) -> pygame.Surface:
    """The influence-radius ring, baked and cached — it is redrawn every frame
    for every node, so it must never be reallocated per frame."""
    key = (radius, alpha)
    cached = _ring_cache.get(key)
    if cached is not None:
        return cached

    size = radius * 2 + 4
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(surface, (*config.COLOR_NODE, alpha),
                       (radius + 2, radius + 2), radius, width=2)
    _ring_cache[key] = surface
    return surface


def draw_node(surface: pygame.Surface, node, is_active: bool) -> None:
    """Influence ring at `node.radius`, lethal core at `node.core_radius`."""
    radius = int(node.radius)
    ring = _ring_sprite(radius, 70 if is_active else 34)
    surface.blit(ring, (int(node.x) - radius - 2, int(node.y) - radius - 2),
                 special_flags=pygame.BLEND_ADD)

    draw_glow(surface, node.x, node.y, config.COLOR_NODE,
              int(node.core_radius * (4 if is_active else 3)))
    pygame.draw.circle(surface, config.COLOR_CORE,
                       (int(node.x), int(node.y)), int(node.core_radius))


def draw_beam(surface: pygame.Surface, px: float, py: float, node,
              charge: Charge, force_magnitude: float, force_max: float) -> None:
    """Thickness and alpha track force magnitude, so the player reads F = k*r
    off the screen without ever being told it."""
    if charge is Charge.NEUTRAL:
        return

    strength = max(0.0, min(1.0, force_magnitude / force_max)) if force_max > 0 else 0.0
    color = (config.COLOR_BEAM_ATTRACT if charge is Charge.ATTRACT
             else config.COLOR_BEAM_REPEL)
    width = max(1, int(1 + strength * 7))
    alpha = int(60 + strength * 195)

    layer = _scratch_layer(surface.get_size())
    pygame.draw.line(layer, (*color, alpha), (px, py), (node.x, node.y), width)
    surface.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)


def draw_player(surface: pygame.Surface, x: float, y: float, radius: float) -> None:
    draw_glow(surface, x, y, config.COLOR_PLAYER, int(radius * 5))
    pygame.draw.circle(surface, config.COLOR_PLAYER, (int(x), int(y)), int(radius))


def draw_trail(surface: pygame.Surface, points) -> None:
    """Fades from tail to head so orbit shape is legible as a drawn line."""
    points = tuple(points)
    if len(points) < 2:
        return
    layer = _scratch_layer(surface.get_size())
    total = len(points)
    for index in range(1, total):
        t = index / total
        alpha = int(8 + 120 * t * t)
        pygame.draw.line(layer, (*config.COLOR_TRAIL, alpha),
                         points[index - 1], points[index], 2)
    surface.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)


def force_magnitude(fx: float, fy: float) -> float:
    return math.hypot(fx, fy)
```

- [ ] **Step 7: Commit**

```bash
git add src/gravi/render/ tests/test_trail.py
git commit -m "feat: neon render primitives with baked additive glow and motion trail"
```

---

### Task 6: Playable loop — control, death, instant restart

**Goal:** Wire input, simulation, and rendering into a loop you can actually play: hold to attract, hold to repel, die on the core, restart instantly.

**Files:**
- Create: `rooms/slice1.json`
- Modify: `main.py` (replace the Task 1 loop body)

**Acceptance Criteria:**
- [ ] Left mouse button or `J` attracts; right mouse button or `K` repels; holding both is neutral
- [ ] The simulation runs at a fixed 240 Hz with an accumulator, independent of frame rate
- [ ] Death is instant and visible; `R` restarts, and restart also clears the trail
- [ ] Death auto-restarts after 0.6 s so the retry loop needs no input
- [ ] The starting room has five nodes placed to allow at least one chain of three orbits
- [ ] The frame loop still awaits `asyncio.sleep(0)`

**Verify:** `python main.py` → hold attract near a node and the player swings around it; fly into a core and the run restarts

**Steps:**

- [ ] **Step 1: Write `rooms/slice1.json`**

Five nodes spread across the frame, spaced so their influence radii overlap only slightly, giving clean single-anchor grabs and a natural left-to-right chain.

```json
{
  "spawn": [180.0, 200.0],
  "width": 1280.0,
  "height": 720.0,
  "nodes": [
    {"x": 330.0,  "y": 430.0, "radius": 240.0, "core_radius": 18.0},
    {"x": 640.0,  "y": 250.0, "radius": 240.0, "core_radius": 18.0},
    {"x": 900.0,  "y": 470.0, "radius": 240.0, "core_radius": 18.0},
    {"x": 1120.0, "y": 240.0, "radius": 200.0, "core_radius": 14.0},
    {"x": 620.0,  "y": 610.0, "radius": 180.0, "core_radius": 22.0}
  ]
}
```

- [ ] **Step 2: Replace the body of `main.py`**

```python
"""Gravi entry point.

The loop is async because pygbag (the browser packager) drives the frame loop
through the JS event loop: without `await asyncio.sleep(0)` each frame the
browser tab locks up. Costs nothing natively, impossible to retrofit cheaply.
"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import pygame

from gravi import config
from gravi.field import Charge, FieldParams, charge_force
from gravi.render import neon
from gravi.render.trail import Trail
from gravi.room import load_room
from gravi.sim import World, charge_from_input

ROOM_PATH = Path(__file__).parent / "rooms" / "slice1.json"
RESPAWN_DELAY = 0.6


def build_world(room, tunables: dict[str, float]) -> World:
    return World(
        room=room,
        params=FieldParams(
            k_attract=tunables["k_attract"],
            k_repel=tunables["k_repel"],
            force_max=tunables["force_max"],
        ),
        gravity_y=tunables["gravity_y"],
        player_radius=tunables["player_radius"],
        speed_max=tunables["speed_max"],
    )


def apply_tunables(world: World, tunables: dict[str, float]) -> None:
    """Push live-edited values into a running world without losing motion."""
    world.params = FieldParams(
        k_attract=tunables["k_attract"],
        k_repel=tunables["k_repel"],
        force_max=tunables["force_max"],
    )
    world.gravity_y = tunables["gravity_y"]
    world.player_radius = tunables["player_radius"]
    world.speed_max = tunables["speed_max"]


async def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption("Gravi")
    clock = pygame.time.Clock()

    tunables = config.default_tunables()
    room = load_room(ROOM_PATH)
    world = build_world(room, tunables)
    trail = Trail(config.TRAIL_MAX_POINTS)

    accumulator = 0.0
    dead_timer = 0.0
    running = True

    while running:
        frame_dt = min(clock.tick(config.TARGET_FPS) / 1000.0, 0.25)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    world.reset()
                    trail.clear()

        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed(num_buttons=3)
        attract_held = keys[pygame.K_j] or mouse[0]
        repel_held = keys[pygame.K_k] or mouse[2]
        charge = charge_from_input(attract_held, repel_held)

        apply_tunables(world, tunables)

        accumulator += frame_dt
        steps = 0
        while accumulator >= world.dt and steps < config.MAX_STEPS_PER_FRAME:
            world.step(charge)
            accumulator -= world.dt
            steps += 1
            if not world.dead:
                trail.add(world.x, world.y)
        if steps == config.MAX_STEPS_PER_FRAME:
            accumulator = 0.0

        if world.dead:
            dead_timer += frame_dt
            if dead_timer >= RESPAWN_DELAY:
                world.reset()
                trail.clear()
                dead_timer = 0.0
        else:
            dead_timer = 0.0

        # --- draw ---
        screen.fill(config.COLOR_BG)
        neon.draw_trail(screen, trail.points())

        active = world.active_node()
        for node in room.nodes:
            neon.draw_node(screen, node, is_active=node is active)

        if active is not None and charge is not Charge.NEUTRAL and not world.dead:
            fx, fy = charge_force(world.x, world.y, active, charge, world.params)
            neon.draw_beam(screen, world.x, world.y, active, charge,
                           math.hypot(fx, fy), world.params.force_max)

        if not world.dead:
            neon.draw_player(screen, world.x, world.y, world.player_radius)

        pygame.display.flip()
        await asyncio.sleep(0)  # REQUIRED for pygbag; do not remove

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Play it**

Run: `python main.py`
Expected: the player falls from the top left; holding `J` or left mouse near the first node whips it around; flying into a bright core restarts the run after a short pause.

- [ ] **Step 4: Run the full suite to confirm nothing regressed**

Run: `pytest -q`
Expected: PASS (all tests from Tasks 1, 3, 4, 5)

- [ ] **Step 5: Commit**

```bash
git add main.py rooms/slice1.json
git commit -m "feat: playable loop — attract/repel control, core death, instant restart"
```

---

### Task 7: Live tuning overlay

**Goal:** Adjust every force constant while playing, with the current values on screen and the ability to save and reload named presets.

**Files:**
- Create: `src/gravi/render/hud.py`
- Create: `src/gravi/tuning.py`
- Create: `presets/default.json`
- Create: `tests/test_tuning.py`
- Modify: `main.py`
- Modify: `.gitignore`

**Acceptance Criteria:**
- [ ] `Tab` toggles the overlay; it starts visible
- [ ] Up/Down select a parameter, Left/Right adjust it by its step, clamped to its bounds
- [ ] Shift multiplies the adjustment step by 10
- [ ] `F5` saves the current values to `presets/current.json`, `F9` reloads them, `F8` restores the built-in defaults
- [ ] Saving in the browser build fails silently rather than raising
- [ ] The overlay shows the derived orbital period `2π/√k_attract`, because that is the number that predicts feel

**Verify:** `pytest tests/test_tuning.py -v` → all pass; then in game, press Down to `gravity_y`, hold Left, and watch the fall slow in real time

**Steps:**

- [ ] **Step 1: Write the failing test `tests/test_tuning.py`**

```python
import json

from gravi import config
from gravi.tuning import TuningState


def test_adjust_moves_by_the_step_for_that_parameter():
    state = TuningState(config.default_tunables())
    state.select("k_attract")
    before = state.values["k_attract"]
    state.adjust(+1)
    assert state.values["k_attract"] == before + config.TUNABLES["k_attract"][1]


def test_adjust_clamps_to_bounds():
    state = TuningState(config.default_tunables())
    state.select("k_attract")
    for _ in range(10_000):
        state.adjust(-1)
    assert state.values["k_attract"] == config.TUNABLES["k_attract"][2]


def test_shift_multiplies_the_step():
    state = TuningState(config.default_tunables())
    state.select("force_max")
    before = state.values["force_max"]
    state.adjust(+1, fast=True)
    assert state.values["force_max"] == before + config.TUNABLES["force_max"][1] * 10


def test_cycle_wraps_around_the_parameter_list():
    state = TuningState(config.default_tunables())
    names = list(config.TUNABLES)
    assert state.selected == names[0]
    state.cycle(-1)
    assert state.selected == names[-1]
    state.cycle(+1)
    assert state.selected == names[0]


def test_orbital_period_matches_the_closed_form():
    import math
    state = TuningState(config.default_tunables())
    state.values["k_attract"] = 4.0
    assert state.orbital_period() == math.pi  # 2*pi/sqrt(4)


def test_save_and_load_round_trips(tmp_path):
    state = TuningState(config.default_tunables())
    state.values["k_attract"] = 17.5
    path = tmp_path / "preset.json"
    assert state.save(path) is True

    fresh = TuningState(config.default_tunables())
    assert fresh.load(path) is True
    assert fresh.values["k_attract"] == 17.5


def test_save_returns_false_on_an_unwritable_path(tmp_path):
    state = TuningState(config.default_tunables())
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    assert state.save(blocker / "nested" / "preset.json") is False


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "preset.json"
    path.write_text(json.dumps({"k_attract": 3.0, "nonsense": 1.0}))
    state = TuningState(config.default_tunables())
    assert state.load(path) is True
    assert state.values["k_attract"] == 3.0
    assert "nonsense" not in state.values


def test_restore_defaults():
    state = TuningState(config.default_tunables())
    state.values["k_attract"] = 99.0
    state.restore_defaults()
    assert state.values["k_attract"] == config.TUNABLES["k_attract"][0]
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_tuning.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gravi.tuning'`

- [ ] **Step 3: Write `src/gravi/tuning.py`**

```python
"""Live tuning state. Pure — no pygame — so the values and the persistence can
be tested without a display.

Feel is found by sweeping values while playing, not by editing a file and
restarting, so this is deliberately in the first slice rather than deferred.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from . import config

FAST_MULTIPLIER = 10.0


class TuningState:
    def __init__(self, values: dict[str, float]) -> None:
        self.values = values
        self._names = list(config.TUNABLES)
        self._index = 0

    @property
    def selected(self) -> str:
        return self._names[self._index]

    def select(self, name: str) -> None:
        self._index = self._names.index(name)

    def cycle(self, direction: int) -> None:
        self._index = (self._index + direction) % len(self._names)

    def adjust(self, direction: int, fast: bool = False) -> None:
        name = self.selected
        _default, step, low, high = config.TUNABLES[name]
        delta = step * direction * (FAST_MULTIPLIER if fast else 1.0)
        self.values[name] = max(low, min(high, self.values[name] + delta))

    def orbital_period(self) -> float:
        """2*pi/sqrt(k_attract). Independent of orbit size under a linear
        central force, which makes it the single best predictor of feel."""
        k = self.values["k_attract"]
        return math.inf if k <= 0 else 2.0 * math.pi / math.sqrt(k)

    def restore_defaults(self) -> None:
        self.values.update(config.default_tunables())

    def save(self, path: str | Path) -> bool:
        """False rather than an exception on failure: the browser build has no
        writable filesystem and a save keypress must not crash the game."""
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as handle:
                json.dump(self.values, handle, indent=2, sort_keys=True)
            return True
        except OSError:
            return False

    def load(self, path: str | Path) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False
        for name in config.TUNABLES:
            if name in data:
                self.values[name] = float(data[name])
        return True
```

- [ ] **Step 4: Run the tuning tests**

Run: `pytest tests/test_tuning.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Write `presets/default.json` and ignore the scratch preset**

`presets/default.json` is the committed starting point. `presets/current.json` is the F5 scratch slot and must not be committed — add this line to `.gitignore`:

```
presets/current.json
```

```json
{
  "force_max": 4000.0,
  "gravity_y": 900.0,
  "k_attract": 8.0,
  "k_repel": 12.0,
  "player_radius": 9.0,
  "speed_max": 2000.0
}
```

- [ ] **Step 6: Write `src/gravi/render/hud.py`**

```python
"""The tuning overlay. Text only, drawn straight over the world."""

from __future__ import annotations

import pygame

from .. import config

_font: pygame.font.Font | None = None

HELP_LINES = (
    "J / LMB attract    K / RMB repel    R restart",
    "TAB overlay   UP/DOWN select   LEFT/RIGHT adjust   SHIFT x10",
    "F5 save preset   F9 load preset   F8 defaults",
    "LMB-drag node   RMB empty add   DEL remove   [ ] radius   , . core",
    "CTRL+S save room",
)


def _get_font() -> pygame.font.Font:
    """`Font(None, ...)` uses pygame's bundled font. SysFont is avoided
    deliberately: the browser build has no system font directory to search."""
    global _font
    if _font is None:
        _font = pygame.font.Font(None, 22)
    return _font


def draw(surface: pygame.Surface, tuning, status: str = "") -> None:
    font = _get_font()
    x, y = 16, 14
    line_height = 19

    def line(text: str, color=config.COLOR_HUD) -> None:
        nonlocal y
        surface.blit(font.render(text, True, color), (x, y))
        y += line_height

    line(f"orbit period  {tuning.orbital_period():6.2f} s   "
         f"(2*pi/sqrt(k_attract) — same at any orbit size)")
    y += 4

    for name in config.TUNABLES:
        is_selected = name == tuning.selected
        marker = ">" if is_selected else " "
        color = (255, 255, 255) if is_selected else config.COLOR_HUD
        line(f"{marker} {name:<14}{tuning.values[name]:10.2f}", color)

    y += 6
    for text in HELP_LINES:
        line(text, (120, 140, 160))

    if status:
        y += 6
        line(status, (255, 230, 140))
```

- [ ] **Step 7: Wire the overlay into `main.py`**

Add these imports next to the existing ones:

```python
from gravi.render import hud
from gravi.tuning import TuningState
```

Add these module constants below `RESPAWN_DELAY`:

```python
PRESET_PATH = Path(__file__).parent / "presets" / "current.json"
STATUS_DURATION = 2.0
```

Replace `tunables = config.default_tunables()` with:

```python
    tuning = TuningState(config.default_tunables())
    tunables = tuning.values
    show_hud = True
    status = ""
    status_timer = 0.0
```

Replace the `elif event.type == pygame.KEYDOWN:` block with:

```python
            elif event.type == pygame.KEYDOWN:
                shift = bool(event.mod & pygame.KMOD_SHIFT)
                ctrl = bool(event.mod & pygame.KMOD_CTRL)
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r and not ctrl:
                    world.reset()
                    trail.clear()
                elif event.key == pygame.K_TAB:
                    show_hud = not show_hud
                elif event.key == pygame.K_UP:
                    tuning.cycle(-1)
                elif event.key == pygame.K_DOWN:
                    tuning.cycle(+1)
                elif event.key == pygame.K_LEFT:
                    tuning.adjust(-1, fast=shift)
                elif event.key == pygame.K_RIGHT:
                    tuning.adjust(+1, fast=shift)
                elif event.key == pygame.K_F5:
                    ok = tuning.save(PRESET_PATH)
                    status = "preset saved" if ok else "save unavailable (browser build)"
                    status_timer = STATUS_DURATION
                elif event.key == pygame.K_F9:
                    ok = tuning.load(PRESET_PATH)
                    status = "preset loaded" if ok else "no preset found"
                    status_timer = STATUS_DURATION
                elif event.key == pygame.K_F8:
                    tuning.restore_defaults()
                    status = "defaults restored"
                    status_timer = STATUS_DURATION
```

A tap gives one precise notch (the `KEYDOWN` above); holding should sweep. Implement the repeat explicitly rather than calling `pygame.key.set_repeat`, which is global and would also strobe Tab and R. Add these constants next to `STATUS_DURATION`:

```python
ADJUST_REPEAT_DELAY = 0.35     # seconds held before the sweep starts
ADJUST_REPEAT_INTERVAL = 0.05  # seconds between notches while sweeping
```

Initialise the timers next to `status_timer = 0.0`:

```python
    adjust_hold = 0.0
    adjust_accum = 0.0
```

And add this right after `charge = charge_from_input(...)`:

```python
        if keys[pygame.K_LEFT] or keys[pygame.K_RIGHT]:
            adjust_hold += frame_dt
            if adjust_hold > ADJUST_REPEAT_DELAY:
                adjust_accum += frame_dt
                fast = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
                direction = 1 if keys[pygame.K_RIGHT] else -1
                while adjust_accum >= ADJUST_REPEAT_INTERVAL:
                    tuning.adjust(direction, fast=fast)
                    adjust_accum -= ADJUST_REPEAT_INTERVAL
        else:
            adjust_hold = 0.0
            adjust_accum = 0.0
```

Add the status countdown right before the draw section:

```python
        if status_timer > 0.0:
            status_timer -= frame_dt
            if status_timer <= 0.0:
                status = ""
```

And draw the overlay immediately before `pygame.display.flip()`:

```python
        if show_hud:
            hud.draw(screen, tuning, status)
```

- [ ] **Step 8: Verify by hand**

Run: `python main.py`
Expected: the overlay lists six parameters with `k_attract` selected. Press Down three times to `gravity_y`, hold Left, and the fall visibly slows. F5 prints "preset saved".

- [ ] **Step 9: Run the suite and commit**

```bash
pytest -q
git add src/gravi/tuning.py src/gravi/render/hud.py presets/default.json tests/test_tuning.py main.py
git commit -m "feat: live tuning overlay with presets and derived orbital period"
```

---

### Task 8: In-session room editing

**Goal:** Drag nodes around, add and delete them, and resize their influence radius and core while playing, so the playtest is not limited to one hand-placed layout.

**Files:**
- Create: `src/gravi/editor.py`
- Create: `tests/test_editor.py`
- Modify: `main.py`

**Acceptance Criteria:**
- [ ] Left-click within a node's core grabs it; dragging moves it; release drops it
- [ ] Right-click on empty space adds a node with default radius and core at the cursor
- [ ] `Delete` removes the node under the cursor
- [ ] `[` and `]` change the hovered node's influence radius; `,` and `.` change its core radius, each clamped to sane bounds
- [ ] `Ctrl+S` saves the room to `rooms/slice1.json`, failing soft in the browser
- [ ] Editing is pure logic in `editor.py` and unit-tested without pygame

**Verify:** `pytest tests/test_editor.py -v` → all pass; then in game, drag a node and watch the influence ring follow

**Steps:**

- [ ] **Step 1: Write the failing test `tests/test_editor.py`**

```python
from gravi.editor import RoomEditor, DEFAULT_CORE_RADIUS, DEFAULT_NODE_RADIUS
from gravi.field import Node
from gravi.room import Room


def make_room():
    return Room(spawn=(100.0, 100.0),
                nodes=[Node(300.0, 300.0, 240.0, 18.0)],
                width=1280.0, height=720.0)


def test_grab_selects_a_node_whose_core_contains_the_cursor():
    editor = RoomEditor(make_room())
    assert editor.grab(305.0, 302.0) is True
    assert editor.dragging is not None


def test_grab_misses_when_the_cursor_is_outside_every_core():
    editor = RoomEditor(make_room())
    assert editor.grab(800.0, 800.0) is False
    assert editor.dragging is None


def test_drag_moves_the_grabbed_node_and_release_stops_it():
    editor = RoomEditor(make_room())
    editor.grab(300.0, 300.0)
    editor.drag(500.0, 450.0)
    node = editor.room.nodes[0]
    assert (node.x, node.y) == (500.0, 450.0)
    editor.release()
    editor.drag(0.0, 0.0)
    assert (editor.room.nodes[0].x, editor.room.nodes[0].y) == (500.0, 450.0)


def test_add_node_appends_with_defaults():
    editor = RoomEditor(make_room())
    editor.add(700.0, 200.0)
    added = editor.room.nodes[-1]
    assert (added.x, added.y) == (700.0, 200.0)
    assert added.radius == DEFAULT_NODE_RADIUS
    assert added.core_radius == DEFAULT_CORE_RADIUS


def test_delete_removes_the_node_under_the_cursor():
    editor = RoomEditor(make_room())
    assert editor.delete(300.0, 300.0) is True
    assert editor.room.nodes == []


def test_delete_is_a_no_op_when_nothing_is_under_the_cursor():
    editor = RoomEditor(make_room())
    assert editor.delete(900.0, 100.0) is False
    assert len(editor.room.nodes) == 1


def test_hovered_uses_the_influence_radius_not_the_core():
    editor = RoomEditor(make_room())
    assert editor.hovered(420.0, 300.0) is editor.room.nodes[0]
    assert editor.hovered(1000.0, 300.0) is None


def test_resize_influence_radius_is_clamped():
    editor = RoomEditor(make_room())
    for _ in range(10_000):
        editor.resize_radius(300.0, 300.0, -1)
    assert editor.room.nodes[0].radius >= 40.0


def test_resize_core_radius_is_clamped_and_stays_below_influence():
    editor = RoomEditor(make_room())
    for _ in range(10_000):
        editor.resize_core(300.0, 300.0, +1)
    node = editor.room.nodes[0]
    assert node.core_radius <= node.radius * 0.5
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_editor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gravi.editor'`

- [ ] **Step 3: Write `src/gravi/editor.py`**

```python
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
```

- [ ] **Step 4: Run the editor tests**

Run: `pytest tests/test_editor.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Wire the editor into `main.py`**

Add the imports:

```python
from gravi.editor import RoomEditor
from gravi.room import load_room, save_room
```

(replacing the existing `from gravi.room import load_room`)

After `world = build_world(room, tunables)` add:

```python
    editor = RoomEditor(room)
```

Add these branches to the `pygame.KEYDOWN` handler, before the closing of that block:

```python
                elif event.key == pygame.K_s and ctrl:
                    ok = save_room(room, ROOM_PATH)
                    status = "room saved" if ok else "save unavailable (browser build)"
                    status_timer = STATUS_DURATION
                elif event.key == pygame.K_DELETE:
                    mx, my = pygame.mouse.get_pos()
                    editor.delete(float(mx), float(my))
                elif event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
                    mx, my = pygame.mouse.get_pos()
                    editor.resize_radius(
                        float(mx), float(my),
                        -1 if event.key == pygame.K_LEFTBRACKET else +1)
                elif event.key in (pygame.K_COMMA, pygame.K_PERIOD):
                    mx, my = pygame.mouse.get_pos()
                    editor.resize_core(
                        float(mx), float(my),
                        -1 if event.key == pygame.K_COMMA else +1)
```

Mouse buttons are already taken: left is attract and right is repel. Gate all editing behind **Alt** so play is never interrupted, and suppress charge while Alt is held so the player is not being yanked around mid-edit.

Add these branches to the event loop:

```python
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if pygame.key.get_mods() & pygame.KMOD_ALT:
                    mx, my = float(event.pos[0]), float(event.pos[1])
                    if event.button == 1:
                        editor.grab(mx, my)
                    elif event.button == 3 and editor.hovered(mx, my) is None:
                        editor.add(mx, my)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                editor.release()
            elif event.type == pygame.MOUSEMOTION and editor.dragging is not None:
                # No Alt check here: releasing Alt mid-drag must not drop the node.
                editor.drag(float(event.pos[0]), float(event.pos[1]))
```

And suppress charge while editing — replace the three input lines with:

```python
        editing = bool(pygame.key.get_mods() & pygame.KMOD_ALT)
        attract_held = (keys[pygame.K_j] or mouse[0]) and not editing
        repel_held = (keys[pygame.K_k] or mouse[2]) and not editing
        charge = charge_from_input(attract_held, repel_held)
```

Update the `HELP_LINES` in `src/gravi/render/hud.py` to reflect the modifier:

```python
    "ALT+LMB drag node   ALT+RMB add   DEL remove   [ ] radius   , . core",
```

- [ ] **Step 6: Verify by hand**

Run: `python main.py`
Expected: holding Alt and dragging a node moves it and its influence ring; Alt+right-click on empty space adds a node; hovering a node and pressing `]` grows its ring; Ctrl+S reports "room saved" and `rooms/slice1.json` changes on disk.

- [ ] **Step 7: Run the suite and commit**

```bash
pytest -q
git add src/gravi/editor.py tests/test_editor.py src/gravi/render/hud.py main.py
git commit -m "feat: in-session room editor — drag, add, delete, resize, save"
```

---

### Task 9: Playtest and rule on the feel

**Goal:** Play the prototype, tune it, and record a verdict against the three criteria in spec §10 — the decision on whether Gravi proceeds past slice 1.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

This is a human judgement task. No agent can close it. The spec commits to not building a generator on top of a mechanic that does not feel good, so this gate blocks every later slice.

**Files:**
- Create: `docs/superpowers/runbooks/2026-08-11-slice-1-feel-verdict.md`
- Modify: `presets/default.json` (replaced with whatever tuning actually won)

**Acceptance Criteria:**
- [ ] At least three distinct tuning presets were played and compared, with `k_attract`, `k_repel`, `gravity_y` and node radius varied between them
- [ ] At least two hand-built node layouts beyond the shipped `rooms/slice1.json` were tested via the editor
- [ ] Criterion 1 recorded with a verdict: three orbits can be chained without deliberate thought
- [ ] Criterion 2 recorded with a verdict: approach angle visibly decides slingshot versus crash
- [ ] Criterion 3 recorded with a verdict: repel reads as a genuine save, not a panic button
- [ ] An explicit PROCEED or STOP decision is written down, with reasoning
- [ ] If PROCEED, the winning values are written into `presets/default.json` and `config.TUNABLES` defaults
- [ ] The browser build is played once as well, confirming the feel survives WASM frame pacing

**Verify:** `docs/superpowers/runbooks/2026-08-11-slice-1-feel-verdict.md` exists, contains a verdict line for all three criteria plus a PROCEED/STOP decision, and `git log` shows the preset commit

**Steps:**

- [ ] **Step 1: Play the shipped room with the default preset**

Run: `python main.py`
Spend at least ten minutes before touching any tuning. Note first impressions while they are still available — they are gone after twenty minutes of exposure.

- [ ] **Step 2: Sweep `k_attract` and record the orbital period that feels best**

The overlay shows `2π/√k_attract`. Try roughly 1.5 s, 2.2 s and 3.5 s periods (`k_attract` ≈ 17.5, 8.0, 3.2). Save each as a preset with F5 after copying `presets/current.json` aside under a name.

- [ ] **Step 3: Sweep `k_repel` and `gravity_y`**

Specifically test whether repel can save a bad approach: aim straight at a core, and try to escape with repel alone. If it cannot, `k_repel` is too low or `force_max` is clamping it.

- [ ] **Step 4: Build two new layouts with the editor**

One with widely spaced small-radius nodes (tests dead-zone-like ballistic travel), one with two overlapping nodes (tests whether single-anchor selection reads correctly when fields overlap). Save each with Ctrl+S after copying the previous room aside.

- [ ] **Step 5: Play the browser build**

Run: `pygbag .` then open `http://localhost:8000`.
Confirm the feel survives — WASM frame pacing is less even than native and the fixed-timestep accumulator is what should absorb it.

- [ ] **Step 6: Write the verdict**

```markdown
# Slice 1 feel verdict

**Date:** <date>
**Build:** <git rev-parse --short HEAD>

## Presets compared

| Preset | k_attract | k_repel | gravity_y | period | Notes |
|---|---|---|---|---|---|
| ... | | | | | |

## Layouts tested

- `rooms/slice1.json` — shipped layout
- <layout 2 name> — <what it was probing>
- <layout 3 name> — <what it was probing>

## Criteria

**1. Three orbits can be chained without deliberate thought.** VERDICT: <yes/no>
<evidence>

**2. Approach angle visibly decides slingshot versus crash.** VERDICT: <yes/no>
<evidence>

**3. Repel reads as a genuine save, not a panic button.** VERDICT: <yes/no>
<evidence>

## Browser build

<did the feel survive WASM frame pacing>

## Decision

**<PROCEED / STOP>**

<reasoning — if PROCEED, what carries into slice 2; if STOP, what specifically
failed and whether any variant of the mechanic is worth another attempt>
```

- [ ] **Step 7: If proceeding, lock in the winning values**

Copy the winning values into `presets/default.json` and update the defaults in `config.TUNABLES` so a fresh session starts at the tuning that won.

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/runbooks/2026-08-11-slice-1-feel-verdict.md presets/default.json src/gravi/config.py
git commit -m "docs: slice 1 feel verdict and locked-in tuning"
```

---

## Notes for whoever executes this

- **Run pytest as `env PYTHONPATH= pytest -q` on this machine.** The dev box sources ROS Jazzy in `.bashrc`, which sets a global `PYTHONPATH` that leaks a broken `launch_testing` plugin into pytest's autoload. Bare `pytest` dies with a traceback that has nothing to do with this project.
- **Never run `python main.py` bare from an agent** — it opens a real window and blocks forever. Use `env PYTHONPATH= SDL_VIDEODRIVER=dummy timeout 5 python main.py; echo "exit=$?"` and treat exit code **124** as the pass signal (a healthy loop ran the full timeout). The real visual check belongs to the human.

- **Task 2 is a stop-the-world task.** If pygbag cannot package the app, do not continue to Task 3 — raise it, because the stack decision and every later task depend on the answer.
- **Do not add dependencies.** Every runtime import has to survive WebAssembly. If something seems to need numpy, it does not in slice 1.
- **Do not let pygame leak into `field.py`, `sim.py`, `room.py`, `tuning.py`, `editor.py` or `render/trail.py`.** `tests/test_purity.py` guards the first three; the others are pure by design because later slices need them headless.
- **The tuning numbers in `config.py` are guesses.** They exist so there is something to sweep from, not because they are right. Task 9 is what makes them real.
