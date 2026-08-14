# Gravi slice 2 — gravity arrows and camera rotation

**Date:** 2026-08-13
**Status:** design, pending approval
**Parent spec:** `2026-08-11-gravi-core-design.md` (§3.1, §3.2, §3.3, §3.6, §8.4, §10)
**Prototypes:** `proto/flip-demo.html`, `proto/terrain-demo.html`

Slice 1 answered "does the mechanic feel good" with a qualified yes. Slice 2
answers a different question: **does rotating the world cost the player their
read of it?** Everything in §3 rests on the claim that Gravi can rotate gravity
for free because it has no directional input. This slice tests that claim.

---

## 1. What decides the verdict

Three criteria, chosen 2026-08-13. All three are judged by playing, not measured.

| # | Criterion | Fails if |
|---|---|---|
| 1 | **No re-orientation beat.** After crossing an arrow you can read your arc and commit to the next grab immediately. | Every flip costs a beat of "wait, where am I". Then the arrow is an interruption, not punctuation, and §3.1's claim that arrows give the run a rhythm is false. |
| 2 | **Comfortable at rate.** Five minutes at the fastest flip frequency we would ship, without motion sickness. | Sickness arrives below the flip rate the escalation schedule (§3.6) wants. That caps an entire escalation axis, which §3.3 already anticipates. |
| 3 | **A bad crossing is your fault.** You can see the arrow coming, and when you cross it badly you know why. | Crossings feel arbitrary. The generator's structural guarantee (§3.1, "the arrow is the seam") then rests on something the player cannot aim at. |

Criterion 3 was originally worded "missing an arrow feels like your fault".
It was reworded after §4.2 changed what missing *means*: with the arrow
spanning the whole far side, you almost never sail past one, so the thing to
judge is the quality of the crossing rather than its occurrence.

**Explicitly not a gate:** whether the fixed-camera option is *pleasant*. §3.3
requires it to exist and §5 below specifies it properly, but slice 2 does not
block on it being as good as the rotating camera.

---

## 2. Scope, and a proposed change to the slice boundary

**This section needs sign-off, because it moves the line §10 draws between
slices 2 and 3.**

§10 lists slice 2 as "gravity arrows and camera rotation" and slice 3 as
"chamber archetypes and streaming". The prototypes showed those cannot be
separated cleanly.

The first prototype put arrows in a single closed arena so the camera would
only ever rotate, never translate. Two playtest findings killed it:

- **Arrows became small targets you aim at.** In a bounded arena an arrow can
  only be a short bar, and hitting one was the hard part. §3.1 describes the
  opposite: the arrow is the chamber's *far side*, something you cross nearly
  every time. "Missing an arrow is recoverable, not fatal" only parses if
  crossing is the default outcome.
- **Arriving at an arrow left nothing in reach.** Keeping node fields clear of
  the arrow band — so arrows would sit on a "far side" — meant arriving with
  no anchor and no recovery. Covering the band with node fields fixed the
  reach but removed the far side. In one arena there is no geometry that
  satisfies both.

A closed arena also produces a failure mode the real game does not have: with
no input the first prototype died 1.7 s after every flip, because inherited
speed became sideways carry and threw the player into a wall. Chambers have no
walls, so the same momentum just yields worse angles — which is exactly what
§3.1 says should happen.

**Proposal.** Slice 2 includes the *minimum* chamber work that makes arrows
mean anything:

**In scope:** a chained chamber corridor with one archetype and fixed
dimensions; streaming (generate ahead, retain a few behind); the exit arrow
spanning a chamber's full far side; gravity as a vector; 90° flips with an
eased camera; the fixed-camera option; death by core contact or leaving a
chamber sideways.

**Out of scope, still slice 3:** archetype *variety*, the parameter box (§4.1),
validation (§4.2), difficulty measurement (§4.3), branching arrows (§3.4),
hazards, and node depletion. The chamber generator here is a scaffold for
judging rotation, not the generator.

**Also out of scope:** score, the path map (§6), the rival (§5).

If this boundary is rejected, the alternative is to keep slice 2 in a single
arena and accept that arrows are tested in a shape the real game never uses —
which is the thing the prototype already showed does not work.

---

## 3. The flip

### 3.1 One eased scalar drives everything

Gravity direction and camera rotation are **the same number**:

```
phi(t)   eased over FLIP_DURATION, 90 degree steps
gravity  = magnitude * (sin phi, cos phi)      # phi = 0 is world-down
camera   maps world -> screen by R(phi) about the player
```

Because the camera rotation is exactly the rotation that carries the gravity
vector onto screen-down, **gravity is straight down on screen at every instant,
including mid-turn.** §3.3's invariant becomes literally true rather than true
only at the endpoints. The world visibly swings around the player; the arc
never bends in a direction the screen does not explain.

The rejected alternative was snapping gravity at the crossing and easing only
the camera. That leaves 0.2 s where the force felt and the screen read
disagree — precisely the moment the player is most disoriented.

### 3.2 Quarter turns are integers

The flip *target* is an integer quarter-turn index; only the eased *current*
angle is a float. Hundreds of flips accumulating `+= pi/2` would drift. A 180°
flip takes the clockwise path by convention, since "shortest path" is
ambiguous there.

### 3.3 The rotation sign is a trap

For `rot(d, a)` implemented as the standard rotation matrix, a direction at
angle φ maps to **φ − a**, not φ + a. Turning the camera by the geometric turn
angle therefore spins the world the *wrong way* on every flip. This bit the
prototype and was caught only by asserting an invariant, not by reading the
code.

**Required test:** once a flip has settled, screen-down must equal the current
chamber's gravity direction. Assert it every step, not at endpoints.

---

## 4. Chambers, arrows, and the entry lane

### 4.1 Chamber geometry

A chamber is a box in its own frame: origin at the entrance line's centre,
`+d` into the chamber (the gravity direction), `+perp(d)` across it. Chambers
chain by placing the next entrance at the previous exit. Prototype values,
which are starting points and not yet tuned: depth 1150, half-width 460.

### 4.2 The arrow spans the whole far side

The exit arrow is a segment across the chamber's full width, perpendicular to
gravity. You cross one nearly every time; **what varies is where on it you
cross.** Crossing outside the span means you left the chamber sideways, which
is death — but the span is the entire chamber, so that is a real mistake and
not a missed target.

An arrow **sets** gravity to its direction; it does not rotate gravity by 90°.
This is §3.1's wording, and it is idempotent: crossing the same arrow twice is
a no-op, and crossing arrows in any order lands somewhere well-defined. A
"rotate by 90°" arrow would make state depend on crossing history, which is
worse to debug and worse to generate levels from.

Trigger is a **segment crossing** — the player's step segment against the
arrow segment — not a proximity disc. There is no radius to fudge, which is
what criterion 3 requires.

### 4.3 Every chamber is entered at offset zero

A consequence of 90° turns that is not obvious and matters a lot:

> The old lateral axis becomes the new depth axis. So the offset at which you
> crossed the arrow becomes your **entry depth** in the next chamber, and your
> lateral offset there is always exactly **zero**.

Derivation: crossing at `P = exit + perp(d)·u`, the next chamber has
`dir' = ±perp(d)` and `perp(dir') = ∓d`. Then
`u' = (perp(d)·u) · perp(dir') = 0`, and `t' = ±u`.

This is a good property — crossing wide means starting deep into the next
chamber and skipping some of its node field; crossing short means starting
behind the entrance and having to fall further. It is real, legible variety
from one geometric fact.

It has a hard corollary. **Every player enters every chamber on the centre
line, so the centre lane must be clear of node cores.** The prototype's
generator placed a core at offset 18 with radius 20 and killed a do-nothing
run in 0.8 s, every time, on that seed. Cores now stay at least 110 px off the
lane while influence rings still reach across it — so there is always
something to grab from the lane, and never anything to hit in it.

**Required test:** over many seeds, no generated core lies within
`core_radius + player_radius + margin` of the centre lane.

---

## 5. The camera

### 5.1 It has to follow

Chambers are larger than the window and chain in 2D, so the camera translates
as well as rotates. This supersedes an earlier decision in this design process
to use a single fully-visible room precisely so the camera would never
translate — that decision was made to avoid follow smoothing, and the arena it
required is what §2 above rejects.

The camera keeps the player at a fixed screen point, set back from centre so
more of the fall ahead is visible.

### 5.2 The fixed-camera option is a branch, not a second renderer

Fixed camera means: do not apply the rotation. Gravity still turns, and the
player watches it turn. Because rotation is a single transform applied at draw
time, this is one branch.

**And nothing else about the framing may move either.** With the camera
rotating, gravity is always screen-down, so the player can sit back from
centre and see more of the fall ahead. With the camera fixed, gravity can
point any way — so the player sits **dead centre**, with equal visibility in
every direction.

The prototype went through both wrong answers first. Keeping the
rotating-mode lead meant sideways gravity flew the player blind into the edge
of the screen. Swinging the lead to follow the gravity vector fixed the
visibility and broke the mode a second way: it panned the view by up to twice
the lead distance on every flip, which reads as a moving camera just as much
as a rotation does. Removing rotation is not enough — **a fixed camera must
have no gravity-driven motion of any kind.** Centring is the only framing that
satisfies that and still shows the player where they are going.

One thing that does keep turning in this mode, unavoidably: the corridor
itself. Chambers chain at right angles, so travelling through them bends the
terrain across the screen. That is the terrain turning, not the camera, and it
is the whole reason the mode gives a stable reference — screen-up never moves,
so the bend is legible as a property of the world rather than of the view.

### 5.3 Rotation happens at draw time

World coordinates never rotate. A `Camera` holds the angle and maps world to
screen per draw call.

This is cheap here for a reason specific to Gravi: **circles are
rotation-invariant.** Nodes, cores, glows and the player are circles, so only
their centre points transform — no pixel rotation at all. Only the trail
polyline, the beam, the arrow bars and the chamber outlines need per-point
work, and `sin`/`cos` are computed once per frame.

It also keeps the sim in unrotated world space, which §8.1 makes
non-negotiable: the validator and trainer must simulate exactly what the game
simulates, and a rotating coordinate system would be a second source of truth.

**Rejected — rotate the finished frame** (`pygame.transform.rotate` on the
rendered surface). At mid-ease angles the output bounding box grows by up to
√2, so it is ~1M pixels resampled plus an allocation every frame, against a
frame that currently costs 1.10 ms. It also resamples rasterised neon, which
blurs and crawls the glow — the exact shimmer §7 says choosing neon *deletes*.

**Rejected — rotate the world data.** Breaks §8.1, makes saved room JSON
meaningless, and the trail history would need rotating too.

---

## 6. The speed clamp must become gravity-relative

Slice 1 clamps world `vx` (carry) and `vy` (fall) separately, so that gravity
stops taxing horizontal carry. With gravity rotating, those axes must be
defined **relative to gravity**:

```
fall  = v · ĝ            clamped to fall_speed_max, downward only
carry = v · perp(ĝ)      clamped to ±speed_max
v     = fall·ĝ + carry·perp(ĝ)
```

At `phi = 0` this reduces to exactly the slice 1 split, so it is a strict
generalisation. Leaving the clamps in world axes would silently undo the carry
fix the moment the player is sideways.

**Required test:** at `phi = 0` the new clamp is byte-for-byte slice 1's
behaviour; and the slice 1 test `test_gravity_never_taxes_horizontal_carry`
must still pass when re-run at `phi = 90°` and `phi = 180°` with the axes
rotated to match — the carry component must be untouched by gravity at any
orientation, not only at zero.

---

## 7. Module map

New:

| Module | Responsibility |
|---|---|
| `gravity.py` | Pure. Eased quarter-turn state: integer target, current angle, `vector(magnitude)`. §8.4 reserves this name. No pygame. |
| `chamber.py` | Pure. Chamber geometry, local coordinates, chain generation and streaming. No pygame. |
| `render/camera.py` | World→screen: rotation, follow, and the gravity-following lead. Precomputes `cos`/`sin` per frame. |

Changed:

| Module | Change |
|---|---|
| `sim.py` | Gravity becomes magnitude + `GravityState`; clamps become gravity-relative; arrow crossing and chamber advance; death by core or sideways exit. |
| `render/neon.py` | Draw functions take a camera. |
| `config.py` | `gravity_y` tunable renamed `gravity` (it is a magnitude now); add `flip_duration`; chamber dimensions. |
| `main.py` | Wire it; a key toggles the fixed camera. |
| `room.py` | Retained for the slice 1 room and the editor, which stay useful for authoring a chamber's node field. |

Renaming the `gravity_y` tunable breaks `presets/default.json`.
`presets/current.json` is gitignored, so only the checked-in default needs
updating.

---

## 8. Testing spine

Beyond the existing 63 tests, which must keep passing:

- **Purity** — `gravity.py` and `chamber.py` must not import pygame
  (`test_purity.py` already enforces this pattern).
- **Gravity** — ease endpoints; integer targets do not drift over hundreds of
  flips; 180° takes the clockwise path.
- **Camera** — identity at angle 0; the player maps to the eye point; and the
  invariant from §3.3, that the rotation carries the gravity vector onto
  screen-down.
- **Sim** — crossing the exit plane advances the chamber and turns gravity;
  crossing outside the span kills; entry lateral offset is always zero (§4.3);
  the clamp reduces to slice 1 at `phi = 0` (§6).
- **Generation** — property test over many seeds: no core in the centre lane;
  the arrow spans the full width; chambers chain without gaps.
- **Render** — the existing pixel-reading tests in `test_neon.py` still pass
  with a camera in the path.

---

## 9. Open questions

- **Flip duration.** §3.3 says roughly 0.2 s. Both prototypes expose it as a
  slider precisely because it is the knob criterion 2 will be judged on.
- **Chamber dimensions.** Depth 1150 and half-width 460 come from the
  prototype and have not been tuned against the tuned speeds.
- **Respawn point.** The prototype respawns at the current chamber's entrance
  rather than the start of the run, to keep a feel test flowing. What the real
  game does is a slice 3 question.
- **Whether `room.py` survives** once chambers exist, or whether the editor
  should author chambers directly.
