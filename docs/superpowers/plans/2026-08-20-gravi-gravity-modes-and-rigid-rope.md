# Gravity modes and the rigid rope — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the slice 2 playtest three gravity modes on one key, a rigid-rope
toggle on another, and a regression test pinning that a gravity swap leaves the
velocity vector alone.

**Architecture:** One pure function in `gravity.py` takes the gravity direction,
the current velocity, the magnitude and `dt`, and returns the velocity after one
step — which is what lets a mode be an added force in two cases and an exact
rotation in the third without `sim.py` knowing which. `sim.py` holds the mode and
the rope flag and calls it; the rope is a position-and-velocity projection
applied after integration. `main.py` binds the keys. Everything defaults to
today's behaviour.

**Tech Stack:** Python 3.12, pygame-ce, pytest. No new dependencies — the
browser build has no install step.

**Spec:** `docs/superpowers/specs/2026-08-20-gravi-gravity-modes-and-rigid-rope-design.md`

**Run tests with:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest`
— the venv lives in the primary checkout, so inside this worktree the house rule
`PYTHONPATH=` becomes `PYTHONPATH=src` against the parent venv. Same ROS
isolation, this worktree's own `src`.

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `src/gravi/gravity.py` | Gravity direction, and now what that direction *does* to a velocity. Pure — imported by the offline validator and the trainer. | Modify: add `GravityMode`, `apply_gravity` |
| `src/gravi/sim.py` | Owns the mode and the rope flag; calls `apply_gravity`; applies the rope constraint | Modify |
| `main.py` | `G` cycles the mode, `T` toggles the rope | Modify |
| `src/gravi/render/hud.py` | One help line | Modify |
| `tests/test_gravity.py`, `tests/test_sim.py`, `tests/test_purity.py` | Tests | Modify |

---

### Task 1: `gravity.py` — the mode and what it does to a velocity

**Goal:** A pure, validator-safe function that returns the velocity after one
step of gravity in a given mode.

**Files:**
- Modify: `src/gravi/gravity.py`
- Test: `tests/test_gravity.py`
- Modify: `tests/test_purity.py:39` (the allowed-import set gains `enum`)

**Acceptance Criteria:**
- [ ] `GravityMode` has `ALONG`, `PERP_CORRIDOR`, `PERP_VELOCITY` and cycles with wraparound
- [ ] `apply_gravity` in `ALONG` returns exactly `v + direction * magnitude * dt`
- [ ] `PERP_VELOCITY` holds `|v|` constant to 1e-9 relative over 10,000 steps
- [ ] `PERP_VELOCITY` turns the heading by `magnitude/|v|` radians per second
- [ ] `PERP_VELOCITY` falls back to `ALONG` below the epsilon rather than stalling
- [ ] `PERP_CORRIDOR` adds no speed along the gravity axis
- [ ] `gravity.py` still imports nothing but `__future__`, `math`, `dataclasses`, `enum`

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_gravity.py tests/test_purity.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gravity.py`:

```python
import pytest

from gravi.gravity import GravityMode, apply_gravity


def test_along_is_the_old_behaviour():
    v = apply_gravity(GravityMode.ALONG, (0.0, 1.0), 30.0, 0.0, 500.0, 1.0 / 240.0)
    assert v == pytest.approx((30.0, 500.0 / 240.0))


def test_perp_corridor_pushes_across_the_gravity_axis():
    """perp(g) with the same handedness as chamber.perp: (-gy, gx)."""
    v = apply_gravity(GravityMode.PERP_CORRIDOR, (0.0, 1.0), 0.0, 0.0,
                      500.0, 1.0 / 240.0)
    assert v == pytest.approx((-500.0 / 240.0, 0.0))


def test_perp_corridor_adds_nothing_along_gravity():
    gx, gy = 0.0, 1.0
    vx, vy = 120.0, 40.0
    for _ in range(500):
        vx, vy = apply_gravity(GravityMode.PERP_CORRIDOR, (gx, gy), vx, vy,
                               500.0, 1.0 / 240.0)
    assert vx * gx + vy * gy == pytest.approx(40.0)


def test_perp_velocity_never_changes_speed():
    """The whole point of the mode. Adding a perpendicular acceleration each
    step instead of rotating walks the velocity off its circle and the speed
    creeps up — invisibly, and in exactly the direction of the complaint this
    mode exists to answer."""
    vx, vy = 300.0, -120.0
    start = math.hypot(vx, vy)
    for _ in range(10_000):
        vx, vy = apply_gravity(GravityMode.PERP_VELOCITY, (0.0, 1.0), vx, vy,
                               500.0, 1.0 / 240.0)
    assert math.hypot(vx, vy) == pytest.approx(start, rel=1e-9)


def test_perp_velocity_turns_the_heading():
    vx, vy = 400.0, 0.0
    before = math.atan2(vy, vx)
    for _ in range(240):                      # one second
        vx, vy = apply_gravity(GravityMode.PERP_VELOCITY, (0.0, 1.0), vx, vy,
                               500.0, 1.0 / 240.0)
    turned = math.atan2(vy, vx) - before
    # omega = magnitude / speed, and speed is preserved, so one second of it.
    assert turned == pytest.approx(500.0 / 400.0, rel=1e-3)


def test_perp_velocity_falls_back_when_stationary():
    """Perpendicular to nothing is undefined, and a player who stopped would
    have nothing left to start them moving: the mode would be a soft-lock."""
    v = apply_gravity(GravityMode.PERP_VELOCITY, (0.0, 1.0), 0.0, 0.0,
                      500.0, 1.0 / 240.0)
    assert v == pytest.approx((0.0, 500.0 / 240.0))


def test_modes_cycle_with_wraparound():
    mode = GravityMode.ALONG
    seen = []
    for _ in range(4):
        seen.append(mode)
        mode = mode.next()
    assert seen == [GravityMode.ALONG, GravityMode.PERP_CORRIDOR,
                    GravityMode.PERP_VELOCITY, GravityMode.ALONG]
```

Confirm `import math` is already at the top of `tests/test_gravity.py`; add it if not.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_gravity.py -q`
Expected: FAIL — `ImportError: cannot import name 'GravityMode'`

- [ ] **Step 3: Implement**

In `src/gravi/gravity.py`, add `from enum import Enum` under the existing
`import math`, and append below `ease_in_out`:

```python
class GravityMode(str, Enum):
    """What the gravity vector DOES to the player. Not what it is — the eased
    quarter-turn in `GravityState` is untouched by all of these, so the camera,
    the flip cadence and the camera lead keep working unchanged.

    Experiments for the slice 2 playtest (see the 2026-08-20 design doc).
    ALONG is the shipped behaviour and the default everywhere.
    """

    ALONG = "along"
    PERP_CORRIDOR = "perp-corridor"
    PERP_VELOCITY = "perp-velocity"

    def next(self) -> "GravityMode":
        order = list(GravityMode)
        return order[(order.index(self) + 1) % len(order)]


# Below this speed, "perpendicular to travel" has no meaning.
PERP_VELOCITY_EPSILON = 1e-6


def apply_gravity(mode: GravityMode, direction: Vec, vx: float, vy: float,
                  magnitude: float, dt: float) -> Vec:
    """The velocity after one step of gravity.

    Returns a VELOCITY rather than an acceleration on purpose: two of these
    modes are a force and the third is a rotation, and only by handing back the
    finished velocity can one function cover both without the caller knowing
    which it got.
    """
    gx, gy = direction
    if mode is GravityMode.ALONG:
        return (vx + gx * magnitude * dt, vy + gy * magnitude * dt)

    if mode is GravityMode.PERP_CORRIDOR:
        # Same handedness as chamber.perp — one convention for "a quarter turn"
        # in this codebase, not two that differ by a sign.
        px, py = -gy, gx
        return (vx + px * magnitude * dt, vy + py * magnitude * dt)

    speed = math.hypot(vx, vy)
    if speed < PERP_VELOCITY_EPSILON:
        # Perpendicular to nothing is undefined, and a stopped player would
        # have nothing left to get them moving again.
        return (vx + gx * magnitude * dt, vy + gy * magnitude * dt)

    # A ROTATION, not an added force. A perpendicular force does no work in
    # continuous mathematics, but explicit Euler at 240 Hz walks the velocity
    # off the circle it is meant to stay on and the speed creeps upward. A
    # rotation is speed-preserving by construction at any step size.
    theta = (magnitude / speed) * dt
    c, s = math.cos(theta), math.sin(theta)
    return (vx * c - vy * s, vx * s + vy * c)
```

- [ ] **Step 4: Widen the purity test's allowed set**

In `tests/test_purity.py`, line 39:

```python
    assert imports <= {"__future__", "math", "dataclasses", "enum"}, imports
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_gravity.py tests/test_purity.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/gravi/gravity.py tests/test_gravity.py tests/test_purity.py
git commit -m "feat(gravity): three modes, with perp-velocity as a rotation"
```

---

### Task 2: `sim.py` — run the mode, and hold the rope

**Goal:** `World` applies gravity through the mode and holds a rigid rope at the
radius recorded when the player grabbed.

**Files:**
- Modify: `src/gravi/sim.py`
- Test: `tests/test_sim.py`

**Acceptance Criteria:**
- [ ] `World` takes `gravity_mode` and `rigid_rope`, both defaulting to today's behaviour
- [ ] Every existing sim test still passes untouched
- [ ] With gravity off, a rigid latch is uniform circular motion: radius and speed both constant
- [ ] The radial component of velocity is removed while rigid
- [ ] Releasing a rigid rope restores free flight
- [ ] Rigid mode does not apply to a repel latch
- [ ] A gravity swap leaves the velocity vector unchanged

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_sim.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sim.py`:

```python
from gravi.gravity import GravityMode


def test_a_rigid_rope_is_uniform_circular_motion():
    """A rope does no work. With gravity off, that means radius AND speed both
    hold — which is the property that separates a constraint from a force."""
    node = Node(400.0, 400.0, 400.0, 5.0)
    w = lab_world(gravity=0.0, nodes=[node], spawn=(300.0, 400.0))
    w.rigid_rope = True
    w.vx, w.vy = 0.0, 260.0

    radii, speeds = [], []
    for _ in range(2400):                      # ten seconds
        w.step(Charge.ATTRACT)
        assert not w.dead
        radii.append(math.hypot(w.x - node.x, w.y - node.y))
        speeds.append(math.hypot(w.vx, w.vy))

    assert max(radii) - min(radii) < 1e-6, (min(radii), max(radii))
    assert max(speeds) - min(speeds) < 1e-6, (min(speeds), max(speeds))
    assert radii[0] == pytest.approx(100.0)


def test_a_rigid_rope_strips_the_radial_velocity():
    node = Node(400.0, 400.0, 400.0, 5.0)
    w = lab_world(gravity=0.0, nodes=[node], spawn=(300.0, 400.0))
    w.rigid_rope = True
    w.vx, w.vy = 200.0, 0.0                    # straight at the node

    w.step(Charge.ATTRACT)

    dx, dy = w.x - node.x, w.y - node.y
    distance = math.hypot(dx, dy)
    radial = (w.vx * dx + w.vy * dy) / distance
    assert radial == pytest.approx(0.0, abs=1e-9)


def test_releasing_a_rigid_rope_restores_free_flight():
    node = Node(400.0, 400.0, 400.0, 5.0)
    w = lab_world(gravity=0.0, nodes=[node], spawn=(300.0, 400.0))
    w.rigid_rope = True
    w.vx, w.vy = 0.0, 260.0
    for _ in range(120):
        w.step(Charge.ATTRACT)
    held = math.hypot(w.x - node.x, w.y - node.y)

    for _ in range(120):
        w.step(Charge.NEUTRAL)

    assert math.hypot(w.x - node.x, w.y - node.y) > held + 50.0


def test_a_rigid_rope_does_not_apply_to_a_repel():
    """A repel is a push, not an attachment."""
    node = Node(400.0, 400.0, 400.0, 5.0)
    w = lab_world(gravity=0.0, nodes=[node], spawn=(300.0, 400.0))
    w.rigid_rope = True
    start = math.hypot(w.x - node.x, w.y - node.y)

    for _ in range(120):
        w.step(Charge.REPEL)

    assert math.hypot(w.x - node.x, w.y - node.y) > start + 10.0


def test_perp_velocity_mode_does_not_feed_the_player_speed():
    w = lab_world(gravity=500.0, nodes=[], spawn=(400.0, 400.0))
    w.gravity_mode = GravityMode.PERP_VELOCITY
    w.vx, w.vy = 300.0, 0.0
    start = math.hypot(w.vx, w.vy)

    for _ in range(1200):
        w.step(Charge.NEUTRAL)
        if w.dead:
            break

    assert math.hypot(w.vx, w.vy) == pytest.approx(start, rel=1e-6)


def test_a_gravity_swap_leaves_the_velocity_alone():
    """Already true, and pinned here because nothing asserted it: crossing an
    arrow changes the FIELD, never the player's velocity vector. It reads like
    a bug to someone tidying up later."""
    w = make_world(flip_duration=0.0)
    ch = _seek_chamber(w, turning=True)
    start = w.chain.at
    w.x, w.y = ch.world(ch.params.depth - 1.0, 40.0)
    w.vx = ch.direction[0] * 500.0 + ch.perp[0] * 220.0
    w.vy = ch.direction[1] * 500.0 + ch.perp[1] * 220.0
    before = (w.vx, w.vy)
    before_gravity = w.gravity_state.direction()

    for _ in range(10):
        w.step(Charge.NEUTRAL)
        if w.chain.at > start:
            break

    assert w.chain.at > start, "the test needs an actual crossing"
    assert w.gravity_state.direction() != pytest.approx(before_gravity)
    # One step of gravity is all that may have changed it, and only along the
    # OLD gravity axis — the vector is never rotated with the field.
    gx, gy = before_gravity
    step = 500.0 / 240.0
    assert w.vx == pytest.approx(before[0] + gx * step, abs=1e-6)
    assert w.vy == pytest.approx(before[1] + gy * step, abs=1e-6)
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_sim.py -q`
Expected: FAIL — `AttributeError: 'World' object has no attribute 'rigid_rope'`

- [ ] **Step 3: Add the two settings to `World.__init__`**

Change the import line in `src/gravi/sim.py`:

```python
from .gravity import QUARTER, GravityMode, GravityState, apply_gravity
```

Add two parameters after `fall_speed_max`, before `dt`:

```python
        gravity_mode: GravityMode = GravityMode.ALONG,
        rigid_rope: bool = False,
```

And in the body, after `self.fall_speed_max = fall_speed_max`:

```python
        # Playtest experiments (2026-08-20 design doc). Both default to the
        # shipped behaviour, so a World built without them is unchanged.
        self.gravity_mode = gravity_mode
        self.rigid_rope = rigid_rope
```

After `self._latch: tuple[int, int] | None = None`:

```python
        self._rope: tuple[int, int] | None = None    # which latch the rope is on
        self._rope_radius: float | None = None
```

- [ ] **Step 4: Route gravity through the mode**

In `step()`, replace this block:

```python
        gx, gy = self.gravity_state.direction()
        # Mass is fixed at 1.0, so force == acceleration.
        ax = gx * self.gravity
        ay = gy * self.gravity

        node = self._update_latch(charge)
        if node is not None:
            # Only attract is allowed to act past the rim; a latched repel is
            # inside its ring by construction, so the cutoff is a no-op there
            # and left in place as a guard rather than an exception.
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=charge is Charge.ATTRACT)
            ax += fx
            ay += fy

        self.vx += ax * self.dt
        self.vy += ay * self.dt
```

with:

```python
        gx, gy = self.gravity_state.direction()
        node = self._update_latch(charge)
        rigid = (self.rigid_rope and node is not None
                 and charge is Charge.ATTRACT)
        self._update_rope(node, rigid)

        # Mass is fixed at 1.0, so force == acceleration. The node force is
        # integrated first and gravity second, because PERP_VELOCITY rotates
        # the finished velocity and has to see the one the node force produced.
        if node is not None and not rigid:
            # Only attract is allowed to act past the rim; a latched repel is
            # inside its ring by construction, so the cutoff is a no-op there
            # and left in place as a guard rather than an exception.
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=charge is Charge.ATTRACT)
            self.vx += fx * self.dt
            self.vy += fy * self.dt
        # A rigid rope supplies exactly the tension its constraint needs, so
        # the spring is NOT applied on top: two mechanisms pulling on one
        # radius would just fight.

        self.vx, self.vy = apply_gravity(self.gravity_mode, (gx, gy),
                                         self.vx, self.vy, self.gravity, self.dt)
```

- [ ] **Step 5: Apply the constraint after integrating**

In `step()`, after `self.elapsed += self.dt` and before `self._check_bounds()`:

```python
        if rigid:
            self._constrain_to_rope(node)

```

Then add both helpers, immediately above `_check_bounds`:

```python
    def _update_rope(self, node: Node | None, rigid: bool) -> None:
        """Record the radius at the moment of the grab, and forget it the
        moment the rope is gone. Keyed on the latch, so re-grabbing a different
        node measures a new radius rather than inheriting the old one."""
        if not rigid:
            self._rope = None
            self._rope_radius = None
            return
        if self._rope != self._latch:
            self._rope = self._latch
            self._rope_radius = math.hypot(node.x - self.x, node.y - self.y)

    def _constrain_to_rope(self, node: Node) -> None:
        """Hold the recorded radius: put the player back on the circle and take
        the radial component out of the velocity. Only the radial part is
        touched, because a rope does no work."""
        if self._rope_radius is None:
            return
        dx = self.x - node.x
        dy = self.y - node.y
        distance = math.hypot(dx, dy)
        if distance < 1e-9:
            return                      # dead centre: no direction to hold
        ux, uy = dx / distance, dy / distance
        self.x = node.x + ux * self._rope_radius
        self.y = node.y + uy * self._rope_radius
        radial = self.vx * ux + self.vy * uy
        self.vx -= radial * ux
        self.vy -= radial * uy
```

- [ ] **Step 6: Clear the rope on reset**

In `reset()`, after `self._latch = None`:

```python
        self._rope = None
        self._rope_radius = None
```

- [ ] **Step 7: Run the whole suite**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q`
Expected: PASS, with 149 existing tests still green

- [ ] **Step 8: Commit**

```bash
git add src/gravi/sim.py tests/test_sim.py
git commit -m "feat(sim): run gravity through the mode, and hold a rigid rope"
```

---

### Task 3: `main.py` — `G` and `T`

**Goal:** The two experiments are reachable while playing, and the HUD says
which state you are in.

**Files:**
- Modify: `main.py`
- Modify: `src/gravi/render/hud.py:12`

**Acceptance Criteria:**
- [ ] `G` cycles the gravity mode, `T` toggles the rope, both with a status flash
- [ ] Both survive `R` (a new run), because they are loop state, not world state
- [ ] The HUD run line names the mode, and says `rigid` when the rope is rigid
- [ ] The help line mentions both keys

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/python /home/ddgg0/.claude/jobs/00519978/tmp/smoke_modes.py` → prints a mode that changed and no traceback

**Steps:**

- [ ] **Step 1: Import the mode in `main.py`**

```python
from gravi.gravity import GravityMode, GravityState  # noqa: E402
```

- [ ] **Step 2: Add the loop state**

Next to `rotating_camera = False`:

```python
    # Playtest experiments (2026-08-20 design doc). Loop state rather than
    # world state, so they survive R and a rebuild of the chain.
    gravity_mode = GravityMode.ALONG
    rigid_rope = False
```

- [ ] **Step 3: Bind the keys**

After the `elif event.key == pygame.K_c:` block:

```python
                elif event.key == pygame.K_g:
                    gravity_mode = gravity_mode.next()
                    status = f"gravity: {gravity_mode.value}"
                    status_timer = STATUS_DURATION
                elif event.key == pygame.K_t:
                    rigid_rope = not rigid_rope
                    status = f"rope: {'rigid' if rigid_rope else 'spring'}"
                    status_timer = STATUS_DURATION
```

- [ ] **Step 4: Push them into the world each frame**

Immediately after the `apply_tunables(world, tunables)` call site:

```python
        world.gravity_mode = gravity_mode
        world.rigid_rope = rigid_rope
```

- [ ] **Step 5: Show them in the HUD**

Change the run line:

```python
            run_line = (f"chambers {world.cleared}   best {max(best, world.cleared)}"
                        f"   distance {int(world.distance)}"
                        f"   camera {'rotating' if rotating_camera else 'fixed'}"
                        f"   gravity {gravity_mode.value}"
                        f"{'   rope rigid' if rigid_rope else ''}")
```

And in `src/gravi/render/hud.py`, line 12:

```python
    "J / LMB attract   K / RMB repel   R new run   C camera   - / = view",
    "G gravity mode   T rigid rope",
```

- [ ] **Step 6: Write the smoke script**

`main.py` has no unit tests, so the binding gets exercised through the real
event loop. Create `/home/ddgg0/.claude/jobs/00519978/tmp/smoke_modes.py`:

```python
"""Boot main.main() headless and press G and T, to prove the bindings reach
the world through the real event loop."""
import asyncio
import os
import pathlib
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, str(pathlib.Path.cwd()))
sys.path.insert(0, str(pathlib.Path.cwd() / "src"))

import pygame  # noqa: E402

import main as game  # noqa: E402

frames = {"n": 0}
real_sleep = asyncio.sleep


async def counted(*args, **kwargs):
    frames["n"] += 1
    n = frames["n"]
    if n == 20:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g,
                                             mod=0, unicode="g"))
    if n == 30:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t,
                                             mod=0, unicode="t"))
    if n > 120:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
    return await real_sleep(0)


asyncio.sleep = counted

seen = {}
real_build = game.build_world


def spy(seed, tunables, chain=None):
    world = real_build(seed, tunables, chain=chain)
    seen["world"] = world
    return world


game.build_world = spy

asyncio.run(game.main())
w = seen["world"]
print("frames:", frames["n"], "gravity_mode:", w.gravity_mode.value,
      "rigid_rope:", w.rigid_rope, "dead:", w.dead)
```

- [ ] **Step 7: Run it**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/python /home/ddgg0/.claude/jobs/00519978/tmp/smoke_modes.py`
Expected: the printed mode is not `along`, `rigid_rope` is True, no traceback

- [ ] **Step 8: Commit**

```bash
git add main.py src/gravi/render/hud.py
git commit -m "feat: G cycles the gravity mode, T toggles the rigid rope"
```

---

### Task 4: rebuild both builds and hand them over

**Goal:** The author can play the experiments in both builds.

**Files:** none (build and process only)

**Acceptance Criteria:**
- [ ] Full suite green
- [ ] `build/web` rebuilt from the current commit, and the packaged
      `src/gravi/gravity.py` contains `perp-velocity`
- [ ] `tools/serve_web.py` serving on 8000, native window relaunched
- [ ] Branch pushed

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q` → all pass, and the packaged-bundle check below prints `True`

**Steps:**

- [ ] **Step 1: Full suite**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q`

- [ ] **Step 2: Rebuild**

```bash
PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pygbag --build main.py
```

- [ ] **Step 3: Confirm the bundle carries the new code**

```bash
python3 -c "import zipfile; z=zipfile.ZipFile('build/web/s1-chambers-and-rotation.apk'); print(b'perp-velocity' in z.read('assets/src/gravi/gravity.py'))"
```
Expected: `True`

- [ ] **Step 4: Serve and relaunch**

```bash
python tools/serve_web.py 8000
PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/python main.py
```

- [ ] **Step 5: Push**

```bash
git push origin worktree-s1-chambers-and-rotation
```

---

## Notes for whoever executes this

- **Do not change any default.** `ALONG` and a spring rope are what the game
  boots with. The slice 2 gate is half-judged on that behaviour, and `field.py`
  is shared with the validator and the trainer.
- **The rope moves the player after `distance` was accumulated** for that step,
  so `distance` is very slightly off while rigid. Left alone deliberately: the
  correction is sub-pixel per step and threading it through would complicate
  the one loop that has to stay readable.
- If `perp-velocity` turns out to leave the player unable to reach an exit, that
  is a finding for the runbook, not a bug to fix — the combo system was
  deferred precisely so play could answer that.
