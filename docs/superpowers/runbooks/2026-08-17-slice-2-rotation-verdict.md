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

PENDING. Requires the five-minute browser playtest below.

## Criteria

| # | Criterion | Verdict | Reasoning |
|---|---|---|---|
| 1 | **No re-orientation beat.** After crossing an arrow you can read your arc and commit to the next grab immediately. | UNJUDGED | Needs play. |
| 2 | **Comfortable at the one rate we ship.** Five minutes at the shipped flip rate, without motion sickness. | UNJUDGED — but see amendment A1 | The author reported the prototype's rotation as nauseating on 2026-08-17, which is what produced A1. That is a report against the *prototype*, not this build, so it is context rather than a verdict. |
| 3 | **A bad crossing is your fault.** You can see the arrow coming, and when you cross it badly you know why. | UNJUDGED | Needs play. |

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
   values into `presets/default.json`.
5. Confirm the fixed camera (now the default) is usable, and say whether the
   rotating one is still worth shipping behind `C`.
6. Fill in the decision line: PROCEED or STOP.

## Coverage gaps

- **Nothing here has been played.** The criteria are feel criteria; no test in
  the suite can stand in for them.
- Native fps and browser fps are both unmeasured. The slice 1 browser-parity
  question is still open, and S4 owns a separate runbook for it.
- The playtest that produced amendment A1 was on `proto/terrain-demo.html`,
  not on this build. Whether the pygame build reads the same way is unknown.
- `chamber_half_width` has never been tuned by anyone, in any build.

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
