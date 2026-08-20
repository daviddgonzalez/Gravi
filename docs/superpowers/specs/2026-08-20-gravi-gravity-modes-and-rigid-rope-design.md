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
behaviour. The game boots behaving as the build the slice 2 gate is being judged
on, and you opt in with a key. Two reasons that matters:

- The slice 2 verdict is still open. Changing what the game does at boot would
  invalidate the playtest that is already half-run.
- `field.py` is shared code, not copied code: the game, the offline validator
  and the trainer all import it (session map invariant 1, core spec §8.1). A
  mode that only exists when a key is pressed cannot desynchronise them.

**"Behaving as", not "bit-for-bit".** Routing gravity through `apply_gravity`
reorders the arithmetic: the old code summed gravity and the node force into one
acceleration and applied it once, and the new code adds the node force to the
velocity and then calls the mode. `ALONG` computes the same quantity, but not in
the same float operations, so a trajectory with a node force acting alongside
gravity diverges at ULP scale — measured 2026-08-20, first difference at step 17
of a 600-step trace, then compounding as any chaotic trajectory does. That is
below anything a player can perceive and no test is sensitive to it (the
determinism test compares the code against itself, not against a recorded
baseline). It is recorded because two future things would care: an input replay
recorded before this change would not reproduce, and S10's ghosts are exactly
that. The reorder is not incidental — `PERP_VELOCITY` rotates the *finished*
velocity, so it has to see the one the node force produced.

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

### 2.2 The speed clamp is mode-aware

An earlier version of this section claimed the clamp "stays exactly as it
is" across all three modes, measuring "fall" along the fixed gravity vector
regardless of mode. That was wrong, and a 2026-08-20 review caught the two
consequences: in `perp-velocity` the velocity rotates freely and sweeps
through that fixed axis, so the clamp truncated it on every crossing — a
player launched at 1500 px/s decayed toward `speed_max` instead of holding
speed, exactly the property this mode exists to guarantee. And in
`perp-corridor` the claim that "fall is across the lane and carry is along
the corridor" was already describing the *intended* axes correctly, but the
code measured both against the fixed gravity vector instead, so
`fall_speed_max` was silently bounding progress and `speed_max` was bounding
the lateral drift — backwards from what is written above. It was invisible
at the shipped defaults only because both caps default to the same value.

The fix (`World._clamp_speed`) measures each mode's fall/carry split against
the axis that mode's gravity actually pushes along, so the split does what
this section always meant it to:

- `along` — fall is along the gravity vector, carry is perpendicular to it.
  Unchanged from slice 1.
- `perp-corridor` — the force here is `perp(gravity)` (see `gravity_force`),
  so *that* is the axis `fall_speed_max` bounds, and the gravity vector
  itself — the axis the force never touches — is carry, bounded by
  `speed_max`. `fall_speed_max` bounds the sideways drift gravity feeds;
  `speed_max` bounds progress down the corridor.
- `perp-velocity` — gravity does no work at all in this mode: it is a
  rotation of the whole velocity vector, not a force along any fixed axis, so
  there is no axis to protect with a fall/carry split. Total speed is clamped
  isotropically at `speed_max` instead. This is not the pathology the split
  exists to avoid — that pathology is gravity continuously adding speed along
  one axis while an isotropic cap makes every other axis pay for it, and here
  gravity adds zero speed on any axis, so there is nothing to pay for.

The eased quarter-turn (`GravityState`) is untouched. Modes change what the
gravity *vector does to the player*, never what the vector *is*, so the camera,
the flip cadence and amendment A3's lead all keep working unchanged.

## 3. The rigid rope

`T` toggles it. Off is today's spring.

When rigid, latching records the distance to the node, and that distance is
then held by advancing the player along the held circle: position and velocity
are both rotated about the node by the angle swept in that step.

**Not** by Euler-stepping in a straight line and reprojecting onto the circle
afterwards, which is what this section said before implementation and which is
wrong for the same reason §2.1 gives. Stripping the radial component measured
*after* a straight-line step multiplies the tangential speed by `cos(theta)`
every step, and that compounds: at the corridor's own scale (`theta` ≈ 0.01
rad/step) a held swing lost ~12% of its speed over ten seconds. Measured on
2026-08-20 by running the reprojection algorithm standalone before it was
wired in. Rotating position and velocity together is speed- and
radius-preserving by construction at any step size.

The radial component is still removed the moment the rope is grabbed, which is
what makes a grab kill inward or outward drift rather than inheriting it.

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

### 3.1 What a mode does while the rope is held

**While a rigid rope is held, gravity is applied as a force increment, never as
a rotation of the whole velocity vector.** Added 2026-08-20 after a review found
`PERP_VELOCITY` and the rope bleeding energy into each other: the mode rotates
the velocity about the origin, which injects a component that is radial relative
to the *node*, and the rope then strips it — every step. Two individually
speed-preserving operations, composed, leaked 260 px/s down to 10 over seventy
seconds while the radius stayed pinned.

With gravity as a force, each mode falls out cleanly:

- `ALONG` and `PERP_CORRIDOR` are forces already. The rope absorbs the radial
  part of the increment and the tangential part accelerates the swing — correct
  pendulum behaviour, and no leak, because what gets projected is a small
  increment rather than the whole velocity.
- `PERP_VELOCITY`'s force is perpendicular to the player's velocity. On a rope
  the velocity is tangential, so that force is *always exactly radial*, so the
  rope absorbs all of it and **gravity does nothing while you are attached**.
  You coast the circle at the speed you brought into it.

That last one is a real rule of the game rather than an accident: a steering
force cannot steer you while the rope decides your direction. Worth watching in
the playtest — it means a rigid rope in `PERP_VELOCITY` is a way to *bank* speed
against gravity.

**A rope shorter than a millimetre is not a rope.** Grabbing at the node's exact
centre divided by zero; a radius of ~1e-6 gave an angular rate of ~1e6 rad/step
and aliased the position into nonsense. Below a 1e-3 radius the rope is ignored
for that step. `field._EPSILON` (1e-9) is deliberately NOT reused: it guards a
force that is separately capped by `force_max`, whereas the rope's angular rate
has no cap at all.

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
