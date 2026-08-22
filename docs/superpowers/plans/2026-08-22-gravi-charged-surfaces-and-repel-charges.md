# Charged surfaces and repel charges — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make corridor walls repel-able surfaces, and give repel a rechargeable
charge cost drawn in light on the player — removing the one death the author
called unlucky, where a gravity flip leaves no node in reach and therefore no
verb available.

**Architecture:** Two new pure functions carry the physics — `Chamber.nearest_wall`
for the geometry and `field.surface_force` for the law — so the offline validator
and trainer see the same code the game does. `sim.py` gains a wall fallback in
the repel path (a node in range always wins) and a charge budget that drains
while pushing and regenerates passively. `render/neon.py` draws the budget as
arcs around the player rather than a HUD bar.

**Tech Stack:** Python 3.12, pygame-ce, pytest. No new dependencies — the browser
build has no install step.

**Spec:** `docs/superpowers/specs/2026-08-22-gravi-charged-surfaces-and-repel-charges-design.md`

**Run tests with:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q`
— the venv lives in the primary checkout, so inside this worktree the house rule
`PYTHONPATH=` becomes `PYTHONPATH=src` against the parent venv. A bare `pytest`
dies before collection because ROS poisons `PYTHONPATH`. **158 tests pass now.**

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `src/gravi/chamber.py` | Corridor geometry. Gains `nearest_wall`. Pure. | Modify |
| `src/gravi/field.py` | The force law, shared with validator and trainer. Gains `surface_force`. Pure. | Modify |
| `src/gravi/config.py` | The six new tunables | Modify |
| `src/gravi/sim.py` | Wall fallback in the repel path; the charge budget | Modify |
| `src/gravi/render/neon.py` | `draw_charges` — the arcs | Modify |
| `main.py` | Passes charge level to the draw | Modify |
| `presets/default.json` | Committed starting values | Modify |

---

### Task 1: `chamber.py` — which wall is nearest, and which way is away from it

**Goal:** A pure geometry helper giving the distance to the nearer side wall and
the inward normal from it.

**Files:**
- Modify: `src/gravi/chamber.py` (add a method to `Chamber`)
- Test: `tests/test_chamber.py`

**Acceptance Criteria:**
- [ ] At the centre lane the distance equals `half_width`
- [ ] At either wall the distance is 0 and the normal points across the corridor, away from that wall
- [ ] A player exactly on the centre lane (`u == 0`) gets a deterministic side
- [ ] A player past a wall gets distance 0, never negative
- [ ] Works in a chamber whose direction is not `(0, 1)`
- [ ] `chamber.py` stays pure — no pygame

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_chamber.py tests/test_purity.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chamber.py`:

```python
def test_the_centre_lane_is_half_a_width_from_either_wall():
    params = ChamberParams(depth=1600.0, half_width=460.0)
    ch = make_chamber(0, (0.0, 0.0), (0.0, 1.0), params, seed=1)
    distance, _normal = ch.nearest_wall(*ch.world(800.0, 0.0))
    assert distance == pytest.approx(460.0)


def test_the_normal_points_away_from_the_nearer_wall():
    params = ChamberParams(depth=1600.0, half_width=460.0)
    ch = make_chamber(0, (0.0, 0.0), (0.0, 1.0), params, seed=1)
    px, py = ch.perp

    distance, normal = ch.nearest_wall(*ch.world(800.0, 460.0))
    assert distance == pytest.approx(0.0)
    assert normal == pytest.approx((-px, -py))

    distance, normal = ch.nearest_wall(*ch.world(800.0, -460.0))
    assert distance == pytest.approx(0.0)
    assert normal == pytest.approx((px, py))


def test_a_player_past_the_wall_gets_zero_not_a_negative_distance():
    """Negative distance would invert the push into a pull. They die on the
    next bounds check either way, but not by being sucked through a wall."""
    params = ChamberParams(depth=1600.0, half_width=460.0)
    ch = make_chamber(0, (0.0, 0.0), (0.0, 1.0), params, seed=1)
    distance, _normal = ch.nearest_wall(*ch.world(800.0, 900.0))
    assert distance == 0.0


def test_the_tie_at_dead_centre_breaks_deterministically():
    """A player at u == 0 is equidistant from both walls. The validator has to
    reproduce whichever side wins, so it must not depend on float noise."""
    params = ChamberParams(depth=1600.0, half_width=460.0)
    ch = make_chamber(0, (0.0, 0.0), (0.0, 1.0), params, seed=1)
    first = ch.nearest_wall(*ch.world(800.0, 0.0))
    for _ in range(5):
        assert ch.nearest_wall(*ch.world(800.0, 0.0)) == first


def test_the_normal_is_perpendicular_to_a_turned_corridor():
    """The corridor runs in world +x here, so its walls are horizontal and the
    normal must be vertical — the method works in chamber-local space, not in
    world axes."""
    params = ChamberParams(depth=1600.0, half_width=460.0)
    ch = make_chamber(0, (0.0, 0.0), (1.0, 0.0), params, seed=1)
    _distance, normal = ch.nearest_wall(*ch.world(800.0, 300.0))
    assert normal[0] == pytest.approx(0.0)
    assert abs(normal[1]) == pytest.approx(1.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_chamber.py -q`
Expected: FAIL — `AttributeError: 'Chamber' object has no attribute 'nearest_wall'`

- [ ] **Step 3: Implement**

In `src/gravi/chamber.py`, add this method to the `Chamber` class, directly after
`local()`:

```python
    def nearest_wall(self, x: float, y: float) -> tuple[float, Vec]:
        """Distance to the nearer side wall, and the unit normal pointing away
        from it, across the corridor.

        The NEARER wall only, never both. At the centre lane two walls push
        equally and cancel, which would delete the force in exactly the middle
        of the corridor — the place a player who just crossed a turn is
        standing (2026-08-22 design doc 3). A player at u == 0 is equidistant,
        so the tie breaks to the +u wall deterministically, because the offline
        validator has to reproduce it.

        Distance is clamped at zero for a player already past the wall. A
        negative distance would invert the push into a pull and suck them
        through it; they die on the next bounds check either way.
        """
        _t, u = self.local(x, y)
        px, py = self.perp
        normal = (-px, -py) if u >= 0.0 else (px, py)
        return (max(0.0, self.params.half_width - abs(u)), normal)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_chamber.py tests/test_purity.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gravi/chamber.py tests/test_chamber.py
git commit -m "feat(chamber): which wall is nearest, and which way is away from it"
```

---

### Task 2: `field.py` — the wall's force law

**Goal:** The repel law for a flat surface, in the module the validator and
trainer share.

**Files:**
- Modify: `src/gravi/field.py`
- Test: `tests/test_field.py`

**Acceptance Criteria:**
- [ ] Force is zero at and beyond the reach
- [ ] Force is `k_repel * reach` at contact, capped by `force_max`
- [ ] Force points along the supplied normal
- [ ] A negative distance is treated as contact, never as a pull
- [ ] `field.py` stays pure — no pygame

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_field.py tests/test_purity.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_field.py` (check `FieldParams` and `surface_force` are
imported at the top; add `surface_force` to the existing `from gravi.field import ...`):

```python
def test_a_surface_pushes_hardest_at_contact_and_nothing_at_the_reach():
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=1e9)
    normal = (1.0, 0.0)

    at_contact = surface_force(0.0, normal, params, 260.0)
    assert at_contact == pytest.approx((15.0 * 260.0, 0.0))

    halfway = surface_force(130.0, normal, params, 260.0)
    assert halfway == pytest.approx((15.0 * 130.0, 0.0))

    assert surface_force(260.0, normal, params, 260.0) == (0.0, 0.0)
    assert surface_force(400.0, normal, params, 260.0) == (0.0, 0.0)


def test_a_surface_force_is_capped_like_every_other_force():
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=100.0)
    force = surface_force(0.0, (1.0, 0.0), params, 260.0)
    assert force == pytest.approx((100.0, 0.0))


def test_a_surface_pushes_along_its_normal():
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=1e9)
    force = surface_force(60.0, (0.0, -1.0), params, 260.0)
    assert force[0] == pytest.approx(0.0)
    assert force[1] < 0.0


def test_a_negative_distance_is_contact_not_a_pull():
    """A player past the wall must never be sucked further through it."""
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=1e9)
    force = surface_force(-50.0, (1.0, 0.0), params, 260.0)
    assert force[0] > 0.0
    assert force == pytest.approx((15.0 * 260.0, 0.0))
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_field.py -q`
Expected: FAIL — `ImportError: cannot import name 'surface_force'`

- [ ] **Step 3: Implement**

Append to `src/gravi/field.py`:

```python
def surface_force(distance: float, normal: Vec, params: FieldParams,
                  reach: float) -> Vec:
    """Repel force from a flat charged surface, pushing along `normal`.

    `normal` must be a unit vector pointing AWAY from the surface, and
    `distance` is how far the player is from it.

    A surface obeys the node's repel law, which core spec 2.3 requires
    ("charged surfaces obey the same law"): strongest at contact, fading
    linearly to nothing at the rim. A wall has no attract case — deferred
    deliberately, see the 2026-08-22 design doc section 7.

    A negative distance means the player is already past the surface. It is
    treated as contact rather than extrapolated, because k*(reach - distance)
    keeps growing out there and, worse, nothing stops the caller from having
    handed us an inward normal — the pair would then pull them further
    through. They die on the next bounds check regardless.
    """
    if reach <= 0.0 or distance >= reach:
        return (0.0, 0.0)
    magnitude = params.k_repel * (reach - max(0.0, distance))
    magnitude = min(max(0.0, magnitude), params.force_max)
    return (normal[0] * magnitude, normal[1] * magnitude)
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q`
Expected: PASS, 158 existing plus the new ones

- [ ] **Step 5: Commit**

```bash
git add src/gravi/field.py tests/test_field.py
git commit -m "feat(field): the repel law for a flat charged surface"
```

---

### Task 3: `config.py` — the six tunables

**Goal:** Every constant in the design is live-adjustable in the overlay, because
none of them is settled.

**Files:**
- Modify: `src/gravi/config.py`
- Modify: `presets/default.json`
- Test: `tests/test_config.py`

**Acceptance Criteria:**
- [ ] All six knobs exist with the design's starting values
- [ ] Every default sits inside its own bounds (the existing sweep test covers this)
- [ ] `presets/default.json` carries the same values

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_config.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_the_surface_and_charge_knobs_are_tunable():
    """None of these is settled, and the playtest sweeps them live."""
    assert config.TUNABLES["wall_reach"].default == 260.0
    assert config.TUNABLES["repel_charges_max"].default == 3.0
    assert config.TUNABLES["repel_charge_seconds"].default == 0.35
    assert config.TUNABLES["repel_min_spend"].default == 0.5
    assert config.TUNABLES["repel_regen"].default == 0.4
    assert config.TUNABLES["repel_attach_bonus"].default == 0.5


def test_a_press_floor_can_never_exceed_the_tank():
    """A floor larger than the maximum would make repel permanently unusable."""
    assert config.TUNABLES["repel_min_spend"].hi <= config.TUNABLES["repel_charges_max"].lo
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL — `KeyError: 'wall_reach'`

- [ ] **Step 3: Implement**

In `src/gravi/config.py`, append inside the `TUNABLES` dict, after the
`turn_gap_max` entry:

```python
    # Charged surfaces and the repel budget (2026-08-22 design doc). wall_reach
    # is node scale on purpose: a player crossing a turn is moving across the
    # corridor at the full speed cap with a wall 0.77 s away, so the reach does
    # not have to span the corridor — pressing early and riding the ramp in is
    # the skill. Measured across twelve seeds; see the doc's section 2.
    "wall_reach":         TunableSpec(260.0, 20.0, 60.0, 900.0),
    # One charge is repel_charge_seconds of push. A press that produces force
    # costs at least repel_min_spend, or a micro-tap is free and the spam this
    # exists to stop comes back wearing a different hat.
    "repel_charges_max":     TunableSpec(3.0,  1.0,  1.0,   9.0),
    "repel_charge_seconds":  TunableSpec(0.35, 0.05, 0.05,  2.0),
    "repel_min_spend":       TunableSpec(0.5,  0.1,  0.0,   1.0),
    # Passive regen is the safety valve, not a convenience: node recovery is
    # unavailable in exactly the nodeless stretch this mechanic exists for.
    "repel_regen":           TunableSpec(0.4,  0.05, 0.0,   4.0),
    "repel_attach_bonus":    TunableSpec(0.5,  0.1,  0.0,   3.0),
```

- [ ] **Step 4: Update the committed preset**

```bash
python3 - <<'PYEOF'
import json, pathlib
p = pathlib.Path("presets/default.json")
d = json.loads(p.read_text())
d.update({"wall_reach": 260.0, "repel_charges_max": 3.0,
          "repel_charge_seconds": 0.35, "repel_min_spend": 0.5,
          "repel_regen": 0.4, "repel_attach_bonus": 0.5})
p.write_text(json.dumps(dict(sorted(d.items())), indent=2) + "\n")
PYEOF
```

- [ ] **Step 5: Run to verify they pass**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/gravi/config.py presets/default.json tests/test_config.py
git commit -m "feat(config): tunables for wall reach and the repel budget"
```

---

### Task 4: `sim.py` — the wall is the fallback surface

**Goal:** When repel is held and no node is in reach, the player pushes off the
nearer wall. This is the task that removes the unlucky death.

**Files:**
- Modify: `src/gravi/sim.py`
- Test: `tests/test_sim.py`

**Acceptance Criteria:**
- [ ] `World` takes `wall_reach`, defaulting to the config value
- [ ] Holding repel with no node in reach pushes away from the nearer wall
- [ ] A node in range still wins — wall force is not added on top
- [ ] Beyond the reach, holding repel does nothing
- [ ] **The integration test:** a player crossing a turn at full speed with no node in reach can change their trajectory with repel before reaching the wall
- [ ] Attract is completely unaffected

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_sim.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sim.py` (add `from gravi.chamber import make_chamber` only
if not already imported; `ChamberParams` and `replace` already are):

```python
def test_repel_pushes_off_the_nearer_wall_when_no_node_is_in_reach():
    """The whole point: a corridor always has a wall, so there is no longer a
    position in the game with no verb available."""
    w = make_world(flip_duration=0.0)          # chamber 0 has no nodes
    ch = w.chain.current
    px, py = ch.perp
    w.x, w.y = ch.world(400.0, 380.0)          # 80 from the +u wall
    w.vx = w.vy = 0.0

    for _ in range(30):
        w.step(Charge.REPEL)

    lateral = w.vx * px + w.vy * py
    assert lateral < -1.0, "must be pushed back toward the centre lane"


def test_a_wall_out_of_reach_does_nothing():
    w = make_world(flip_duration=0.0, wall_reach=100.0)
    ch = w.chain.current
    px, py = ch.perp
    w.x, w.y = ch.world(400.0, 0.0)            # 460 from either wall
    w.vx = w.vy = 0.0

    for _ in range(30):
        w.step(Charge.REPEL)

    lateral = w.vx * px + w.vy * py
    assert lateral == pytest.approx(0.0, abs=1e-9)


def test_a_node_in_range_wins_over_the_wall():
    """The wall is the fallback, not an extra force stacked on node play."""
    ch_params = ChamberParams(depth=1600.0, half_width=460.0)
    node = Node(0.0, 0.0, 300.0, 10.0)         # placed below, then moved onto us
    w = make_world(nodes=[node], flip_duration=0.0, chamber_params=ch_params)
    ch = w.chain.current
    here = ch.world(400.0, 380.0)
    near = ch.world(300.0, 380.0)              # 100 away, well inside its ring
    w.chain.chambers[0] = replace(
        w.chain.chambers[0],
        nodes=(Node(near[0], near[1], 300.0, 10.0),))
    w.x, w.y = here
    w.vx = w.vy = 0.0

    w.step(Charge.REPEL)

    # The node is BELOW the player along the corridor, so a node push moves
    # them along +t. A wall push would move them across, along -u. Only one of
    # those may happen.
    t_component = w.vx * ch.direction[0] + w.vy * ch.direction[1]
    assert t_component > 0.0, "the node, not the wall, must be pushing"


def test_a_player_crossing_a_turn_can_save_themselves_on_a_wall():
    """The death this whole design exists to remove. Cross a turn at full
    speed with nothing to grab, hold repel, and the trajectory must change
    before the wall arrives — see the 2026-08-22 design doc, section 2."""
    w = make_world(flip_duration=0.0)
    ch = _seek_chamber(w, turning=True)
    start = w.chain.at
    w.x, w.y = ch.world(ch.params.depth - 2.0, 0.0)
    w.vx = ch.direction[0] * 600.0
    w.vy = ch.direction[1] * 600.0
    for _ in range(20):
        w.step(Charge.NEUTRAL)
        if w.chain.at > start:
            break
    assert w.chain.at > start, "the test needs an actual crossing"

    nxt = w.chain.current
    # Strip the node field so the wall really is the only thing available.
    # chambers[0].index is the oldest retained chamber, which is how you turn a
    # chamber index into a list position without touching a private attribute.
    w.chain.chambers[w.chain.at - w.chain.chambers[0].index] = replace(
        nxt, nodes=())
    nxt = w.chain.current
    px, py = nxt.perp
    before = w.vx * px + w.vy * py

    for _ in range(120):                        # half a second
        w.step(Charge.REPEL)
        if w.dead:
            break

    after = w.vx * px + w.vy * py
    assert abs(after) < abs(before), (
        f"repel must bleed off the lateral rush: {before} -> {after}")
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_sim.py -q`
Expected: FAIL — `TypeError: make_world() got an unexpected keyword argument 'wall_reach'`

- [ ] **Step 3: Thread `wall_reach` through the test helper**

In `tests/test_sim.py`, add `wall_reach=260.0` to `make_world`'s signature and
pass it into `World(...)`. `lab_world` forwards through `make_world`, so it needs
no change.

- [ ] **Step 4: Implement in `src/gravi/sim.py`**

Change the field import line:

```python
from .field import Charge, FieldParams, Node, charge_force, surface_force
```

Add a parameter to `World.__init__`, after `rigid_rope`:

```python
        wall_reach: float = 260.0,
```

and in the body, beside the other assignments:

```python
        # Corridor walls are repel-able surfaces (2026-08-22 design doc). A
        # corridor always has one, which is what removes the no-verb moment
        # after a gravity turn.
        self.wall_reach = wall_reach
```

In `step()`, replace this block:

```python
        if node is not None and not rigid:
            # Only attract is allowed to act past the rim; a latched repel is
            # inside its ring by construction, so the cutoff is a no-op there
            # and left in place as a guard rather than an exception.
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=charge is Charge.ATTRACT)
            ax += fx
            ay += fy
```

with:

```python
        if node is not None and not rigid:
            # Only attract is allowed to act past the rim; a latched repel is
            # inside its ring by construction, so the cutoff is a no-op there
            # and left in place as a guard rather than an exception.
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=charge is Charge.ATTRACT)
            ax += fx
            ay += fy
        elif node is None and charge is Charge.REPEL:
            # No node in reach, so the wall is what is left. It is a FALLBACK,
            # never an extra force stacked on node play: a node in range always
            # wins the branch above. The rule a player can hold in their head is
            # "the wall is what you have when you have nothing else".
            distance, normal = self.chain.current.nearest_wall(self.x, self.y)
            fx, fy = surface_force(distance, normal, self.params,
                                   self.wall_reach)
            ax += fx
            ay += fy
```

- [ ] **Step 5: Run the whole suite**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q`
Expected: PASS. If an existing test fails, STOP and report — attract and the
rigid rope must be untouched by this.

- [ ] **Step 6: Commit**

```bash
git add src/gravi/sim.py tests/test_sim.py
git commit -m "feat(sim): the wall is the fallback surface when no node is in reach"
```

---

### Task 5: `sim.py` — repel costs charge

**Goal:** Repel drains a rechargeable budget, so it is a timing decision rather
than a button to hold.

**Files:**
- Modify: `src/gravi/sim.py`
- Test: `tests/test_sim.py`

**Acceptance Criteria:**
- [ ] `World` starts with a full tank and exposes `repel_charges`
- [ ] Charge drains only while repel produces force; a press in open space is free
- [ ] A press that produced force costs at least `repel_min_spend`
- [ ] Repel does not fire at all below `repel_min_spend`
- [ ] Regen is passive, pauses while draining, and never exceeds the maximum
- [ ] A new attract latch grants `repel_attach_bonus`, once per latch, not per frame
- [ ] `reset()` refills the tank
- [ ] Attract costs nothing
- [ ] Core spec §2.3 carries the amendment that permits the meter

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_sim.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sim.py`:

```python
def test_a_press_in_open_space_is_free():
    """The player is allowed to be wrong about whether anything was in reach."""
    w = make_world(flip_duration=0.0, wall_reach=10.0)
    ch = w.chain.current
    w.x, w.y = ch.world(400.0, 0.0)
    before = w.repel_charges
    for _ in range(60):
        w.step(Charge.REPEL)
    assert w.repel_charges == pytest.approx(before)


def test_a_push_drains_the_tank():
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    w.x, w.y = ch.world(400.0, 380.0)
    before = w.repel_charges
    for _ in range(60):                          # a quarter second of pushing
        w.step(Charge.REPEL)
    assert w.repel_charges < before


def test_a_tap_costs_at_least_the_floor():
    """Without the floor, a micro-tap is free and tap-spam replaces hold-spam."""
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    w.x, w.y = ch.world(400.0, 380.0)
    before = w.repel_charges

    w.step(Charge.REPEL)                         # one frame: 1/240 s
    w.step(Charge.NEUTRAL)                       # released

    spent = before - w.repel_charges
    assert spent == pytest.approx(0.5, abs=1e-9)


def test_repel_does_not_fire_on_an_empty_tank():
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    px, py = ch.perp
    w.x, w.y = ch.world(400.0, 380.0)
    w.repel_charges = 0.0
    w.vx = w.vy = 0.0

    w.step(Charge.REPEL)

    assert (w.vx * px + w.vy * py) == pytest.approx(0.0, abs=1e-9)


def test_the_tank_regenerates_and_caps():
    """Gravity off and a wide chamber, so the player never dies: reset() refills
    the tank, and a test that let them die would pass without regen existing."""
    w = lab_world(gravity=0.0, nodes=[])
    w.repel_charges = 0.0
    for _ in range(240 * 30):                    # thirty seconds
        w.step(Charge.NEUTRAL)
        assert not w.dead
    assert w.repel_charges == pytest.approx(w.repel_charges_max)


def test_regen_pauses_while_pushing():
    """Drain and regen must never fight over the same frame, or the cost of a
    push is quietly refunded as it is paid."""
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    w.x, w.y = ch.world(400.0, 380.0)
    w.repel_charges = 2.0

    for _ in range(60):
        w.step(Charge.REPEL)

    # Floor plus a quarter second of drain, with nothing added back.
    expected = 2.0 - max(0.5, (60 / 240) / w.repel_charge_seconds)
    assert w.repel_charges == pytest.approx(expected, abs=1e-6)


def test_a_new_attract_latch_pays_a_bonus_once():
    node = Node(400.0, 400.0, 300.0, 5.0)
    w = lab_world(gravity=0.0, nodes=[node], spawn=(300.0, 400.0))
    w.repel_charges = 0.0

    w.step(Charge.ATTRACT)
    after_first = w.repel_charges
    assert after_first >= w.repel_attach_bonus

    for _ in range(10):
        w.step(Charge.ATTRACT)
    # Regen still ticks while attracting, so allow for it — what must NOT
    # happen is a second bonus, which would be another whole attach_bonus.
    assert w.repel_charges < after_first + w.repel_attach_bonus


def test_reset_refills_the_tank():
    w = make_world(flip_duration=0.0)
    w.repel_charges = 0.0
    w.reset()
    assert w.repel_charges == pytest.approx(w.repel_charges_max)
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_sim.py -q`
Expected: FAIL — `AttributeError: 'World' object has no attribute 'repel_charges'`

- [ ] **Step 3: Thread the knobs through the test helper**

In `tests/test_sim.py`, add these to `make_world`'s signature and pass them into
`World(...)`: `repel_charges_max=3.0, repel_charge_seconds=0.35,
repel_min_spend=0.5, repel_regen=0.4, repel_attach_bonus=0.5`.

- [ ] **Step 4: Add the state to `World.__init__`**

After `self.wall_reach = wall_reach`, add the parameters (in the signature, after
`wall_reach`):

```python
        repel_charges_max: float = 3.0,
        repel_charge_seconds: float = 0.35,
        repel_min_spend: float = 0.5,
        repel_regen: float = 0.4,
        repel_attach_bonus: float = 0.5,
```

and in the body:

```python
        # Repel's budget (2026-08-22 design doc 4). Attract has no cost and
        # must not gain one: solid cores already make holding attract fatal,
        # which is what makes the pull self-limiting. Nothing makes holding
        # repel fatal, because it pushes you away from the thing that would
        # punish you, so the push was unlimited by omission rather than design.
        self.repel_charges_max = repel_charges_max
        self.repel_charge_seconds = repel_charge_seconds
        self.repel_min_spend = repel_min_spend
        self.repel_regen = repel_regen
        self.repel_attach_bonus = repel_attach_bonus
        self.repel_charges = repel_charges_max
        self._press_paid: float | None = None   # None when no press is open
        self._press_used = 0.0
        self._bonus_latch: tuple[int, int] | None = None
```

In `reset()`, after the rope lines:

```python
        self.repel_charges = self.repel_charges_max
        self._press_paid = None
        self._press_used = 0.0
        self._bonus_latch = None
```

- [ ] **Step 5: Add the accounting helpers**

Add these two methods to `World`, immediately above `_check_bounds`:

```python
    def _open_or_continue_press(self) -> bool:
        """Pay for a repel that is about to produce force. False means it may
        not fire.

        The floor is deducted the instant the first force is produced, not on
        release, so a press can never drain past what it reserved. A press that
        produces NO force never gets here and therefore costs nothing.
        """
        if self._press_paid is None:
            if self.repel_charges < self.repel_min_spend:
                return False
            self.repel_charges -= self.repel_min_spend
            self._press_paid = self.repel_min_spend
            self._press_used = 0.0

        self._press_used += self.dt / max(self.repel_charge_seconds, 1e-9)
        overrun = self._press_used - self._press_paid
        if overrun > 0.0:
            spend = min(overrun, self.repel_charges)
            self.repel_charges -= spend
            self._press_paid += spend
            if spend < overrun:
                return False            # tank ran dry mid-push
        return True

    def _end_press(self) -> None:
        self._press_paid = None
        self._press_used = 0.0
```

- [ ] **Step 6: Wire the accounting into `step()`**

Replace the force block you wrote in Task 4 with this. The candidate force is
computed BEFORE paying, because a press that produces nothing is free:

```python
        if node is not None and not rigid:
            # Only attract is allowed to act past the rim; a latched repel is
            # inside its ring by construction, so the cutoff is a no-op there
            # and left in place as a guard rather than an exception.
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=charge is Charge.ATTRACT)
        elif node is None and charge is Charge.REPEL:
            # No node in reach, so the wall is what is left. It is a FALLBACK,
            # never an extra force stacked on node play: a node in range always
            # wins the branch above. The rule a player can hold in their head is
            # "the wall is what you have when you have nothing else".
            distance, normal = self.chain.current.nearest_wall(self.x, self.y)
            fx, fy = surface_force(distance, normal, self.params,
                                   self.wall_reach)
        else:
            fx = fy = 0.0

        pushing = False
        if charge is Charge.REPEL and (fx != 0.0 or fy != 0.0):
            # Only a push that would actually do something costs anything.
            pushing = self._open_or_continue_press()
            if not pushing:
                fx = fy = 0.0
        else:
            self._end_press()

        ax += fx
        ay += fy

        if not pushing:
            # Regen and drain never fight over the same frame.
            self.repel_charges = min(
                self.repel_charges_max,
                self.repel_charges + self.repel_regen * self.dt)
```

Then, directly after the `self._update_rope(node, rigid)` line, add the attach
bonus:

```python
        if (charge is Charge.ATTRACT and node is not None
                and self._latch != self._bonus_latch):
            # Once per NEW latch, not per frame: grabbing is already how you
            # steer, and now it is also how you rearm.
            self._bonus_latch = self._latch
            self.repel_charges = min(
                self.repel_charges_max,
                self.repel_charges + self.repel_attach_bonus)
        elif node is None:
            self._bonus_latch = None
```

- [ ] **Step 7: Run the whole suite**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q`
Expected: PASS. Existing repel tests may now be affected by the budget — if one
fails because it holds repel for longer than the tank allows, give that test an
explicit large `repel_charges_max` rather than weakening its assertion, and say
so in your report.

- [ ] **Step 8: Write the core spec amendment**

The design doc's §6 requires this, and it is the reason the meter is allowed to
exist at all. In `docs/superpowers/specs/2026-08-11-gravi-core-design.md`, at the
END of §2.3 (after the "Charged surfaces obey the same law" paragraph), append:

```markdown
> **Amendment — 2026-08-22. Repel has a cost; attract does not.**
>
> This section stands unchanged for **attract**: the solid core is still the
> entire balance system for the pull, still geometric, still no meter. Approach
> angle still decides whether a node is a slingshot or a wall, and that is still
> the deep skill.
>
> **Repel** gains a rechargeable charge cost, because the argument above does
> not reach it. Solid cores make holding attract fatal, which is what makes the
> pull self-limiting. Nothing makes holding repel fatal — it pushes you *away*
> from the thing that would punish you — so the pull's geometric limiter has no
> equivalent on the push, and repel was unlimited by omission rather than by
> design. An unlimited emergency out is a button you simply hold whenever you
> are unsure.
>
> The cost is drawn **in light on the player**, not in a UI panel, so §11's
> "no meter or UI" holds as to UI and is amended as to meter.
>
> Repel's job here — "the emergency out when an approach was misjudged" — is
> strengthened rather than weakened, because charged surfaces now make that out
> available where no node exists, which is exactly where it used to be missing.
>
> See `docs/superpowers/specs/2026-08-22-gravi-charged-surfaces-and-repel-charges-design.md`.
```

- [ ] **Step 9: Commit**

```bash
git add src/gravi/sim.py tests/test_sim.py docs/superpowers/specs/2026-08-11-gravi-core-design.md
git commit -m "feat(sim): repel costs a rechargeable charge"
```

---

### Task 6: the readout — arcs of light around the player

**Goal:** The budget is visible without a UI bar.

**Files:**
- Modify: `src/gravi/render/neon.py`
- Modify: `main.py`
- Test: `tests/test_neon.py`

**Acceptance Criteria:**
- [ ] `draw_charges` draws one arc per whole charge, in the repel hue
- [ ] A full tank reads brighter than an empty one at the same pixel
- [ ] A partial charge draws a partly-lit arc rather than all-or-nothing
- [ ] Arc radius scales with the camera's view, like every other world length
- [ ] `main.py` passes the live charge level

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_neon.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_neon.py`:

```python
def test_a_full_charge_ring_reads_brighter_than_an_empty_one(screen):
    """The budget has to be legible without a UI bar — it is drawn on the
    player, in the colour of the verb it powers (2026-08-22 design doc 5)."""
    cam = Camera(800, 600)
    cam.update(400.0, 300.0, angle=0.0, rotating=False, lead=0.0)

    screen.fill(config.COLOR_BG)
    neon.draw_charges(screen, 400.0, 300.0, 3.0, 3.0, 12.0, cam)
    full = sum(peak_brightness(screen, 400 + dx, 300 + dy)
               for dx, dy in ((28, 0), (-28, 0), (0, 28), (0, -28)))

    screen.fill(config.COLOR_BG)
    neon.draw_charges(screen, 400.0, 300.0, 0.0, 3.0, 12.0, cam)
    empty = sum(peak_brightness(screen, 400 + dx, 300 + dy)
                for dx, dy in ((28, 0), (-28, 0), (0, 28), (0, -28)))

    assert full > empty


def test_a_partial_charge_reads_between_empty_and_full(screen):
    cam = Camera(800, 600)
    cam.update(400.0, 300.0, angle=0.0, rotating=False, lead=0.0)
    levels = []
    for charge in (0.0, 1.5, 3.0):
        screen.fill(config.COLOR_BG)
        neon.draw_charges(screen, 400.0, 300.0, charge, 3.0, 12.0, cam)
        levels.append(sum(peak_brightness(screen, 400 + dx, 300 + dy)
                          for dx, dy in ((28, 0), (-28, 0), (0, 28), (0, -28))))
    assert levels[0] < levels[1] < levels[2]
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/test_neon.py -q`
Expected: FAIL — `AttributeError: module 'gravi.render.neon' has no attribute 'draw_charges'`

- [ ] **Step 3: Implement in `src/gravi/render/neon.py`**

Append:

```python
CHARGE_GAP = 0.22          # radians of blank between arcs


def draw_charges(surface: pygame.Surface, x: float, y: float,
                 charges: float, charges_max: float, player_radius: float,
                 camera) -> None:
    """The repel budget, as arcs orbiting the player.

    Drawn on the player and in the repel hue rather than as a bar in a corner,
    because in this game light IS the ruleset (spec section 7) and a resource
    should speak the same language as the force it pays for. A partly-spent
    charge dims its own arc rather than vanishing, so the reading is continuous
    like the beam's intensity is.
    """
    whole = max(1, int(round(charges_max)))
    radius = camera.scale_length(player_radius) * 2.4
    if radius < 4.0:
        return                          # too small to read; do not draw noise
    sx, sy = camera.to_screen(x, y)
    span = (2.0 * math.pi / whole) - CHARGE_GAP
    box = pygame.Rect(int(sx - radius), int(sy - radius),
                      int(radius * 2), int(radius * 2))

    for index in range(whole):
        filled = max(0.0, min(1.0, charges - index))
        if filled <= 0.0:
            continue
        start = index * (2.0 * math.pi / whole) + CHARGE_GAP * 0.5
        pygame.draw.arc(surface, _scaled(config.COLOR_BEAM_REPEL, filled),
                        box, start, start + span, 2)
```

Add `import math` at the top if it is not already there (it is — `force_magnitude`
uses it).

- [ ] **Step 4: Wire it into `main.py`**

Find the player draw and add the charges immediately after it, so the arcs sit
over the player's glow:

```python
        if not world.dead:
            neon.draw_player(screen, world.x, world.y, world.player_radius, camera)
            neon.draw_charges(screen, world.x, world.y, world.repel_charges,
                              world.repel_charges_max, world.player_radius,
                              camera)
```

- [ ] **Step 5: Push the new tunables into the world**

In `main.py`'s `build_world`, add to the `World(...)` call:

```python
        wall_reach=tunables["wall_reach"],
        repel_charges_max=tunables["repel_charges_max"],
        repel_charge_seconds=tunables["repel_charge_seconds"],
        repel_min_spend=tunables["repel_min_spend"],
        repel_regen=tunables["repel_regen"],
        repel_attach_bonus=tunables["repel_attach_bonus"],
```

and in `apply_tunables`, so sweeping them live works without a rebuild:

```python
    world.wall_reach = tunables["wall_reach"]
    world.repel_charges_max = tunables["repel_charges_max"]
    world.repel_charge_seconds = tunables["repel_charge_seconds"]
    world.repel_min_spend = tunables["repel_min_spend"]
    world.repel_regen = tunables["repel_regen"]
    world.repel_attach_bonus = tunables["repel_attach_bonus"]
```

- [ ] **Step 6: Run the suite, then the headless smoke**

```bash
PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q
PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/python /home/ddgg0/.claude/jobs/00519978/tmp/smoke_modes.py
```

The smoke must still print a frame count and `dead: False` with no traceback.

- [ ] **Step 7: Commit**

```bash
git add src/gravi/render/neon.py main.py tests/test_neon.py
git commit -m "feat(render): the repel budget is arcs of light, not a bar"
```

---

### Task 7: rebuild both builds and hand them over

**Goal:** The author can play charged surfaces and the charge budget in both
builds.

**Files:** none (build and process only)

**Acceptance Criteria:**
- [ ] Full suite green
- [ ] The packaged bundle contains `surface_force` and `draw_charges`
- [ ] `tools/serve_web.py` serving on 8000, native window relaunched
- [ ] Branch pushed

**Verify:** `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q` → all pass, and the packaged-bundle check below prints `True True`

**Steps:**

- [ ] **Step 1: Full suite**

Run: `PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pytest tests/ -q`

- [ ] **Step 2: Rebuild**

```bash
PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/pygbag --build main.py
```

- [ ] **Step 3: Confirm the bundle carries the new code**

A build timestamp is not proof — the archive changes whenever anything in the
directory does, including the pytest cache.

```bash
python3 -c "import zipfile; z=zipfile.ZipFile('build/web/s1-chambers-and-rotation.apk'); print(b'surface_force' in z.read('assets/src/gravi/field.py'), b'draw_charges' in z.read('assets/src/gravi/render/neon.py'))"
```
Expected: `True True`

- [ ] **Step 4: Serve and relaunch**

```bash
pkill -f "serve_web.py"
pkill -f "^/home/ddgg0/projects/Gravi/.venv/bin/python main.py"
/home/ddgg0/projects/Gravi/.venv/bin/python tools/serve_web.py 8000
PYTHONPATH=src /home/ddgg0/projects/Gravi/.venv/bin/python main.py
```

(The last two run in the background.)

- [ ] **Step 5: Push**

```bash
git push origin worktree-s1-chambers-and-rotation
```

---

## Notes for whoever executes this

- **Attract must not gain a cost.** If a test or a refactor makes attract spend
  charge, that is a bug, not a simplification. Core spec §2.3 explains why the
  pull is self-limiting and the push is not.
- **The wall is a fallback, never an addition.** If both a node force and a wall
  force are ever applied in the same step, the feature has changed meaning.
- **The integration test in Task 4 is the point of the whole plan.** If it is
  hard to make pass, that is a finding about the design, not a test to loosen.
- Wall *attract* is deliberately out of scope (design doc §7). Do not add it.
