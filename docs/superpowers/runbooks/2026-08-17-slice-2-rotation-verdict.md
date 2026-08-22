# Slice 2 rotation verdict

**Status: OPEN — not yet judged.** Everything below the line marked *machine
evidence* is verified. The three criteria are judged by playing, and nobody
has played this build yet, so the decision line stays PENDING rather than
being filled in from a build that merely boots. Slice 1's verdict recorded
exactly this gap ("built and booted, not played in a browser") and it is still
open; writing PROCEED here without playing would close it dishonestly.

**Build under test:** `e274af8` (branch `worktree-s1-chambers-and-rotation`)
**Built with:** `PYTHONPATH=src .venv/bin/pygbag --build main.py` → `build/web/index.html`

## Decision

PENDING. Criteria 1 and 3 have been played and answered (2026-08-22);
criterion 2 and the numbers are still outstanding. Flip cadence after A4 —
a turn every 3–7 chambers — was reported good.

## Criteria

| # | Criterion | Verdict | Reasoning |
|---|---|---|---|
| 1 | **No re-orientation beat.** After crossing an arrow you can read your arc and commit to the next grab immediately. | **YES** (2026-08-22) | Author, after playing the post-A4 build: "the no re-orientation beat test is good". |
| 2 | **Comfortable at the one rate we ship.** Five minutes at the shipped flip rate, without motion sickness. | UNJUDGED — but see amendment A1 | The author reported the prototype's rotation as nauseating on 2026-08-17, which is what produced A1. That is a report against the *prototype*, not this build, so it is context rather than a verdict. |
| 3 | **A bad crossing is your fault.** You can see the arrow coming, and when you cross it badly you know why. | **MOSTLY — one named exception** (2026-08-22) | Author: "the only deaths that feel unlucky are when you flip gravities and no nodes are near". So the criterion holds for crossings the player misjudged, and fails for one specific case: gravity turns, the new fall direction has nothing grabbable in reach, and there is no play available. That is not a crossing the player got wrong — it is a chamber with no answer. See "The one unlucky death" below. |

## The one unlucky death

Reported 2026-08-22, and the only thing standing between criterion 3 and a
clean yes: **you flip gravity and there is nothing in reach to grab.** Every
other death the author reported reads as earned.

Worth being precise about whose fault this is. It is not the flip and it is not
the camera — the author passed criterion 1 in the same breath. It is that the
player's only two verbs both require a node, so a moment with no node in reach
is a moment with no verb. Core spec §2.3 already anticipated this and assigned
the answer: *"Repel gets a permanent job: the emergency out when an approach was
misjudged"*, and *"Charged surfaces obey the same law. Repel off a wall to
launch without touching it."* A corridor always has walls. Today they are only
lethal boundaries, never surfaces you can push off, so the emergency out exists
in the spec and not in the game.

Two candidate fixes, and they pull in opposite directions:

- **Charged surfaces (repel off a wall).** Directly removes the no-verb moment,
  because a wall is always there. Already specced, already one of the five
  entity types, escalation table introduces them at chambers 4–8.
- **A repel charge budget.** Requested by the author the same day. This makes
  the emergency out *scarce*, which by itself would make this exact death class
  **worse**, not better — an empty meter at the moment of a flip is precisely a
  moment with no verb. If both ship, the budget must never be the reason the
  out was unavailable during a flip.

## What changed during implementation

**Amendment A1 — flip rate is not a difficulty axis** (slice 2 spec §1, core
spec §3.3 and §3.6). Decided by the author mid-implementation: the rotation is
nauseating, and raising the flip rate is not allowed to be how the game gets
harder. Consequences: flip rate is one comfort constant, never sampled per
chamber or fed to a difficulty score (binds S2, S6, S11); timed auto-flips are
struck from the escalation table; **the game opens with the fixed camera**,
with `C` toggling to the rotating one.

Because the fixed camera is now the default, the slice 2 spec's "explicitly
not a gate: whether the fixed camera is *pleasant*" is weaker than it was. It
is now the default experience. Slice 2 still does not block on it matching the
rotating camera, but a playtest that finds it unpleasant is a finding worth
recording rather than a non-issue.

**Amendment A2 — field of view is a knob** (slice 2 spec §1, §5.1, §9). Also
requested by the author mid-playtest: you must be able to see far enough ahead
to plan a grab. `view_width` (both cameras) and `camera_lead` (rotating only)
are draw-time tunables; world lengths scale with the view, screen furniture does
not, and the set of chambers drawn — nodes included — is derived from the view
so a widened view can never show an outline with no node field in it. A1's
no-pan invariant is untouched: the fixed camera still gets no lead.

**Amendment A3 — the fixed camera leads along gravity** (slice 2 spec §5.2,
reversed). A2's wider view was not what was wanted; room *in front* was. The
lead follows the gravity vector, which is why it is safe on a camera that does
not rotate, and it is scaled per axis so falling and running sideways get the
same share of the travel axis ahead. `camera_lead = 0` restores the old
strictly centred camera. `view_width` reverted to 1:1.

**Amendment A4 — gravity turns every 3–7 chambers**, not every one. Chambers
between run straight and draw no arrow. Flip frequency is now depth × cadence.
§4.3's zero-offset entry is a property of turns only; straight seams carry the
player's offset through.

**A test that was passing for the wrong reason.**
`test_core_contact_kills_in_a_neighbouring_chamber_too` dropped the player onto
a generated node of the *next* chamber. With every chamber turning, that put
them outside the corridor and they died of leaving it — the assertion passed
without a core ever being touched. Straight chambers put the same node a full
depth further along the same axis, which made the crossing back-up rewind the
player 1253 units and exposed it. It now plants a node just past the seam and
asserts the player is still in the current chamber when it kills them.

**Two generator/sim corrections** found by the tests rather than by play:

1. Sampling node offsets uniformly across the chamber's half-width produced
   chambers with *nothing reachable from the centre lane* (seed 20, chamber 3:
   four nodes, no influence ring crossing the lane). Every chamber is entered
   at offset zero, so that is a corridor you enter with nothing to grab. The
   generator now alternates a lane anchor with a wide node.
2. Crossing the exit arrow landed the player wherever the fixed step
   overshot, so entry offset into the next chamber was a leftover fraction of
   a step (−1.5 px measured) rather than the exact zero spec §4.3 requires.
   The crossing now backs up along the step's velocity to the precise point
   where it met the arrow plane. The prototype has the same overshoot; it is
   too small to see, which is why it survived.

**Lab mode spawn.** `--room` ran the slice 1 room as one looping chamber but
spawned on the corridor's centre lane at (640, 60) — directly above that
room's core at (640, 250), so it died instantly, every loop. The lab chamber
now keeps the room's authored spawn of (180, 200).

## Winning values

**Not yet chosen.** `presets/default.json` still holds the pre-playtest
defaults, which are the prototype's tuned values:

| Knob | Value | Note |
|---|---|---|
| `flip_duration` | 0.30 | Spec §9 open question; criterion 2 is judged on it |
| `chamber_depth` | 1600.0 | ~8 gravity swaps/minute in the prototype (1150 gave ~26 and read as too hard) |
| `chamber_half_width` | 460.0 | Untuned, straight from the prototype |
| `gravity` | 500.0 | Renamed from `gravity_y`; a magnitude now |
| `view_width` | 1280.0 | 1:1. Raised to 2200 on 2026-08-19 and reversed the same day (A3): a wider view was not what was asked for. Bound to `-`/`=` for sweeping |
| `camera_lead` | 0.22 | Room in front, on BOTH cameras since A3. Untuned |
| `turn_gap_min` / `turn_gap_max` | 3 / 7 | Amendment A4. Chosen from play, not swept |
| `rigid_rope` | `True` | Not a tunable, a `World` default. Playtested 2026-08-20 against the spring (the 2026-08-20 gravity-modes-and-rigid-rope doc's experiment); the rigid rope won. `ALONG` stayed the winning gravity mode, and the other two modes (`PERP_CORRIDOR`, `PERP_VELOCITY`) were removed from the code that same day — `ALONG` is the only gravity behaviour left, unconditionally. The spring is still reachable behind `T` |

Force-law constants (`k_attract` 15.0, `k_repel` 15.0, `force_max` 4500.0,
`speed_max` 600.0, `fall_speed_max` 600.0) are **unchanged from slice 1**. See
"For other sessions" below.

## Supporting evidence (machine)

- `PYTHONPATH=src .venv/bin/pytest tests/ -q` → **117 passed** (slice 1's
  baseline was 63). Note the command: the venv lives in the primary checkout,
  so inside a worktree the house-rule `PYTHONPATH=` becomes `PYTHONPATH=src`
  against the parent venv. Same ROS isolation, worktree's own `src`.
- `PYTHONPATH=src .venv/bin/pygbag --build main.py` → succeeds;
  `build/web/index.html` plus a 190 KB apk.
- Headless boot of `main()` under the dummy SDL driver, 400 frames: the run
  crosses an arrow, retains the cleared chamber's outline, accumulates
  distance, no traceback.
- Headless boot of `main() --room rooms/slice1.json`, 600 frames: 7 laps of
  the lab chamber, no deaths, editor path live.
- The gravity-onto-screen-down invariant is asserted at **every step** of a
  flip, not just its endpoints (`tests/test_camera.py`).
- The lane-clearance property holds over 300 seeds; a wider sweep of 300 seeds
  × 30 chambers found 0 chambers with nothing reachable from the lane.

## Still to do — the gate

1. Serve `build/web` and **play it in a browser for at least five minutes**,
   chaining crossings. `docs/web-build.md` has the recipe.
2. Record fps and physics-step saturation from the in-game overlay as numbers.
3. Judge criteria 1, 2 and 3 with an explicit yes/no each, and say why.
4. Sweep `flip_duration` and `chamber_depth` while playing; write the winning
   values into `presets/default.json`. Note that `F5` writes
   `presets/current.json` (the gitignored scratch slot), so the winning numbers
   have to be copied across deliberately.
5. Sweep `camera_lead` (room in front) and `view_width` (room in every
   direction) and answer A2/A3's open question: how much corridor has to be
   ahead of the player before a grab two chambers away is plannable rather than
   a surprise. Sweep `turn_gap_min`/`turn_gap_max` too — A4 set them from play
   at 3–7 without a sweep, and they now set flip frequency together with
   `chamber_depth`.
6. Confirm the fixed camera (now the default) is usable, and say whether the
   rotating one is still worth shipping behind `C`. Because the fixed camera may
   not lead (A1, A2), widening the view is the only room-ahead it gets — say
   whether that is enough.
7. Fill in the decision line: PROCEED or STOP.

## Coverage gaps

- **Nothing here has been played.** The criteria are feel criteria; no test in
  the suite can stand in for them.
- Native fps and browser fps are both unmeasured. The slice 1 browser-parity
  question is still open, and S4 owns a separate runbook for it.
- The playtest that produced amendment A1 was on `proto/terrain-demo.html`,
  not on this build. Whether the pygame build reads the same way is unknown.
- `chamber_half_width` has never been tuned by anyone, in any build.
- Neither field-of-view knob has been tuned by anyone (A2, A3), and the turn
  cadence (A4) was chosen from play rather than swept. The unit
  tests prove the transform is correct and that widening cannot pan the fixed
  camera; nothing proves a given width is *readable*.
- The browser build was hung behind a static server that 404s `/cdn/` until
  2026-08-18, so no browser session before that date got past click-to-start.
  See `docs/web-build.md`.

## For other sessions

- **The force-law constants did not move.** `k_attract`, `k_repel`,
  `force_max`, `gravity`, `speed_max` and `fall_speed_max` are exactly slice
  1's values. They are **not yet frozen** — the playtest above may still move
  them, so S7 must not bake a shipped chamber library until this runbook says
  PROCEED and names them final (core spec §4.4).
- **S2:** flip rate is barred from the parameter box and the difficulty record
  (A1). `ChamberParams` is the placeholder your parameter box replaces;
  `ChamberChain.outlines` is retained from the first commit for S10.
- **S6:** archetypes may not vary flip rate.
- **S11:** flip rate is not an escalation curve to tune.
