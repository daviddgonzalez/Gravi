# Gravity modes and the rigid rope

**Status:** approved 2026-08-20. Experiments for the slice 2 playtest, not
shipped behaviour.

**Origin.** The author, mid-playtest: *"acceleration feels uncontrollable when
the acceleration should be from players swinging."* Today gravity pulls along
the corridor, so speed arrives whether or not you earned it, and a swing is
something you do to steer the fall rather than the thing that makes you fast.
Three experiments test whether that can be inverted.

## 1. What this is not

**Not a change to the shipped force law.** Every mode here defaults to today's
behaviour. The game boots identical to the build the slice 2 gate is being
judged on, and you opt in with a key. Two reasons that matters:

- The slice 2 verdict is still open. Changing what the game does at boot would
  invalidate the playtest that is already half-run.
- `field.py` is shared code, not copied code: the game, the offline validator
  and the trainer all import it (session map invariant 1, core spec §8.1). A
  mode that only exists when a key is pressed cannot desynchronise them.

**If a mode wins the playtest, that changes.** It becomes part of the force law
S7 has to freeze before baking a chamber library (session map invariant 2), and
this document is superseded by whatever slice-level spec adopts it.

**No combo system.** It was proposed alongside these and deliberately deferred:
if gravity stops feeding the player speed, whether they end up starved is a
question play answers, and a mechanic tuned before that question is answered is
tuned blind.

## 2. Gravity modes

One key (`G`) cycles three modes. The HUD names the current one.

| Mode | What gravity does |
|---|---|
| `along` | Today. Accelerates the player down the corridor. |
| `perp-corridor` | The same push rotated a quarter turn across the lane. Constant within a chamber, changes only at a turn. |
| `perp-velocity` | Acts at 90° to however the player is currently moving. Cannot change their speed at all — only their heading. |

### 2.1 `perp-velocity` is a rotation, not a force

The whole point of `perp-velocity` is that gravity stops being a source of
speed. A perpendicular force does no work in continuous mathematics, but this
game integrates explicit Euler at 240 Hz, and adding a perpendicular
acceleration each step walks the velocity **off** the circle it is supposed to
stay on. Speed creeps upward — slowly, invisibly, and in exactly the direction
of the complaint this experiment exists to answer.

So it is implemented as an exact rotation of the velocity vector:

```
omega = magnitude / |v|        # radians per second
v' = rotate(v, omega * dt)
```

Speed-preserving by construction, at any step size. `|v|` in the denominator is
the physically correct term — a perpendicular force of fixed magnitude bends a
fast object less than a slow one — and it also means a fast player is barely
steered while a drifting one is whipped around, which is a behaviour the
playtest should look at rather than a bug.

**Degenerate case.** At `|v| ~ 0` the direction is undefined, and worse, a
player who stops has nothing to make them move again: the mode would be a
soft-lock. Below a small epsilon it falls back to `along` for that step. This
is a real design compromise, not an implementation detail — in `perp-velocity`
the only thing that gets a motionless player moving is gravity behaving like it
does in `along`.

**Handedness** is fixed, not random or player-chosen: one consistent direction
of curl, or the mode is unlearnable. It uses the same handedness as `perp()` in
`chamber.py` — `perp(v) = (-v_y, v_x)` — so there is one convention in the
codebase for "rotated a quarter turn" rather than two that differ by a sign,
which is the family of bug this subsystem has already produced once.

### 2.2 What the modes do not change

The gravity-relative speed clamp stays exactly as it is, and stays meaningful:

- In `along`, unchanged.
- In `perp-corridor`, "fall" is across the lane and "carry" is along the
  corridor, so `fall_speed_max` bounds sideways drift and `speed_max` bounds
  progress.
- In `perp-velocity`, gravity is perpendicular to travel by definition, so the
  fall component is always ~0 and total speed is bounded by `speed_max` alone.

The eased quarter-turn (`GravityState`) is untouched. Modes change what the
gravity *vector does to the player*, never what the vector *is*, so the camera,
the flip cadence and amendment A3's lead all keep working unchanged.

## 3. The rigid rope

`T` toggles it. Off is today's spring.

When rigid, latching records the distance to the node, and that distance is
then held: each step the position is projected back onto the circle and the
radial component of velocity is removed.

Three decisions worth stating:

1. **Attract only.** A repel is a push, not an attachment. Rigid mode does not
   apply to it.
2. **The `k·r` attract force is not applied while rigid.** A rope supplies
   exactly the tension its constraint needs; a spring pulling as well would be
   two mechanisms fighting over the same radius. The beam still draws — it is
   the rope.
3. **Slice 1's "the rope never snaps at the rim" rule becomes moot** while
   rigid, because the radius cannot grow past the rim in the first place. The
   rule stays for spring mode.

The constraint does no work: with gravity off, a rigid latch is uniform
circular motion, and that is the property to test it by.

## 4. Velocity across a gravity swap

Already the behaviour, and this exists to keep it that way. Crossing an arrow
changes the gravity field and nothing else — the velocity vector is not rotated
with it. Measured 2026-08-20: a player crossing at `(-220, 500)` with gravity
swapping from down to right came out at `(-220, 502)`, and the 2 px/s is one
240 Hz step of gravity, not a rotation.

Nothing currently asserts this, so a regression test does. It is the kind of
property that reads like a bug to someone tidying up later.

## 5. Where the code goes

| Unit | Responsibility |
|---|---|
| `gravity.py` | `GravityMode`, and one pure function taking the gravity direction, the velocity, the magnitude and `dt`, returning the new velocity. Pure, no pygame, importable by the validator. |
| `sim.py` | Holds the mode and the rope flag; calls that function instead of adding `g·dt` inline; applies the rope constraint after integrating. |
| `main.py` | `G` cycles the mode, `T` toggles the rope, HUD shows both. |

Returning a **velocity** rather than an acceleration is what lets one function
cover both an added force and a rotation without callers knowing which is which.

## 6. Testing

- `perp-velocity` holds speed constant to floating-point tolerance over
  thousands of steps, while the heading demonstrably turns. This is the test
  that would have caught the naive implementation.
- `perp-velocity` falls back rather than stalling at `|v| = 0`.
- `perp-corridor` adds no speed along the corridor axis.
- `along` is unchanged — the existing suite already covers it, and must stay
  green untouched.
- Rigid rope: radius constant across a long swing; radial velocity removed on
  latch; with gravity off, uniform circular motion at constant speed.
- Releasing a rigid rope restores free flight.
- A gravity swap leaves the velocity vector alone (§4).

## 7. Open questions for the playtest

- Does `perp-velocity` leave the player fast enough to reach an exit, or is a
  combo system needed after all?
- Is `|v|`-dependent steering (fast = barely curved, slow = whipped) readable,
  or does it feel inconsistent?
- Does a rigid rope make the swing more controllable, or just more rigid?
- Do the modes interact with the turn cadence (A4) — is a straight run under
  `perp-corridor` a corridor you cross sideways?
