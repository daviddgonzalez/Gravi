# Slice 1 feel verdict

**Date:** 2026-08-12
**Build:** `428f32a`
**Judged by:** David Daniel Gonzalez, playing the native build

Slice 1 exists to answer one question: does the polarity mechanic feel good
enough to build a game on? This is the answer.

## Decision

**PROCEED.**

The core loop holds up. All three criteria in spec §10 came back yes, one of
them with a reservation recorded below. Gravi continues past slice 1 into the
chamber and generation work.

## Criteria

| # | Criterion (spec §10) | Verdict |
|---|---|---|
| 1 | Three orbits can be chained without deliberate thought | **Yes, with reservations** |
| 2 | Approach angle visibly decides slingshot versus crash | **Yes** |
| 3 | Repel reads as a genuine save, not a panic button | **Yes** |

**Criterion 1 reservation.** Chaining works, but it is not yet thoughtless —
it takes conscious effort to keep a chain going. Not a blocker for proceeding;
it is the thing to watch when chamber generation starts producing layouts,
since a layout that demands deliberate planning per grab will read as harder
than its measured difficulty suggests (§4.3).

## What changed during the playtest

The influence radius originally broke the connection the moment the player
crossed it, and it broke constantly at exactly the moment the player was
committed to a swing. The rule is now: **the ring decides where you can grab,
not how long you can hold.** A connection persists until released.

This amends spec §2.2, which specified the opposite. The new rule and its two
consequences — attract keeps tightening past the rim, repel floors at zero so
it cannot invert into a pull — are written up as §2.2.1.

The change is what moved criterion 1 from failing to passing.

## Winning values

Adopted as both `presets/default.json` and the `config.TUNABLES` defaults:

| Parameter | Value | Was |
|---|---|---|
| `k_attract` | 15.0 | 8.0 |
| `k_repel` | 15.0 | 12.0 |
| `force_max` | 4500.0 | 4000.0 |
| `gravity_y` | 500.0 | 900.0 |
| `speed_max` | 600.0 | 2000.0 |
| `player_radius` | 7.0 | 9.0 |

Derived orbital period at `k_attract = 15`: **1.62 s**, independent of orbit
size. A comfortable chain rhythm measured headless was roughly 1.0 s held then
0.33 s released — about two thirds of a lap per grab.

## Supporting evidence

A headless probe swept hold/release policies over `rooms/slice1.json`:

| Configuration | Longest chain |
|---|---|
| Shipped defaults (`gravity_y` 900, `k_attract` 8), rim breaks the rope | 1 node |
| Same layout, `gravity_y` 250 / `k_attract` 14, rim breaks the rope | 4 nodes |
| Playtested values, rope holds until released | 4 nodes |

At the original defaults gravity carried the player out of bounds in 1.27 s and
no chain formed under any policy in the sweep, which is what prompted the
tuning pass. Test suite at the time of the verdict: 52 passing.

## Coverage gaps

Recorded plainly rather than papered over. None of these changed the decision,
but the verdict rests on a narrower base than Task 9 originally asked for:

- **Presets compared: 2, not 3.** The shipped defaults and the playtested
  values, plus the headless gravity/`k_attract` sweep. No third hand-played
  preset.
- **Layouts tested: 1.** Only the shipped `rooms/slice1.json`. The in-session
  editor shipped and works (9 tests) but was not used to build alternative
  layouts during the session.
- **Browser build: not played.** The browser was verified booting and
  rendering during the Task 2 gate, on the blank loop only. The full game has
  been rebuilt and served but not played in the browser, so **the claim that
  the feel survives WASM frame pacing is untested.**

The browser playthrough is the gap worth closing first — frame pacing under
WASM is exactly the kind of thing that changes a timing-based feel, and the
build is already sitting there.
