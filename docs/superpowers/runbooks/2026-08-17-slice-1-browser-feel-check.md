# Browser feel check

**Date:** 2026-08-17, rebuilt 2026-08-30 against slice 2
**Build:** `f276b10` — S4 merged with main, i.e. slice 2 (chambers, gravity
vector, camera, charged surfaces, repel charges)
**Judged by:** _not yet — awaiting a human at a keyboard_
**Status:** **INCOMPLETE.** The build half is done and recorded. The verdict
half needs someone to play it. Do not cite this runbook as an answer until the
Verdict section is filled in.

Does the game's feel survive WebAssembly frame pacing? This runbook is where
that gets answered.

## What changed on 2026-08-30, and what it costs us

This was originally written to test a build byte-identical to the judged slice 1
commit `79fd949`, deliberately **before** the slice 2 work merged, so that a bad
result would isolate WASM from new game code.

**That window has closed.** Slice 2 merged to `main` (`f52e03f`), and the build
now under test is slice 2. The consequence, stated plainly so nobody has to
rediscover it: **a bad result here no longer distinguishes "WASM is slow" from
"slice 2 is slow".** If the browser feels wrong, the follow-up is to run the
native build of the same commit and compare, which is a second measurement this
runbook does not have.

The upside is that the thing being judged is the game people would actually
play, not an artifact three weeks stale.

## Agent-side results

**Build — PASS.**

    $ PYGBAG=/path/to/.venv/bin/pygbag tools/build_web.sh
    build/web contents:
    -rw-r--r-- favicon.png           18477
    -rw-r--r-- index.html            12122
    -rw-r--r-- s4-ship-layer.apk    297343
    -rw-r--r-- s4-ship-layer.tar.gz 249532

    total size: 572K  (apk: 292K)

The archive is named after the directory pygbag packaged, not after the
project — from a normal `Gravi/` checkout it is `gravi.apk`. See
docs/web-build.md.

The package grew from 176K to 292K across the slice 2 merge, which is the
cheapest available confirmation that the new code actually made it in.

**Package contents — PASS.** 78 entries; `main.py`, `src/gravi/chamber.py`,
`src/gravi/gravity.py` and `src/gravi/render/camera.py` all present. This
catches the packaging failure that shows up in a browser as a permanently grey
screen.

**Suite — PASS.** 220 passed on the merge commit.

**Headless frame cost — PASS, native.** Not a browser number, but the baseline
the browser number has to be read against. 600 frames, seed 1, dev box (WSL2):

| camera | mean | p95 | max | draw | sim |
|---|---|---|---|---|---|
| fixed (the default) | 1.252 ms | 2.742 ms | 9.186 ms | 1.177 ms | 0.075 ms |
| rotating | 1.082 ms | 2.136 ms | 7.190 ms | 1.020 ms | 0.062 ms |

About 7.5% of a 16.67 ms frame budget. For reference, the same probe on slice 1
measured 0.905 ms mean / 0.016 ms sim — the corridor costs roughly 40% more per
frame to draw and the simulation got ~4× more expensive, both expected from
drawing several chambers instead of one room.

Two things worth reading off that table:

- The renderer still costs ~16× the simulation. If the browser is slower, look
  at the draw path first.
- Both camera modes produce an **identical checksum**
  (`-248.201387,3345.000000,225,1,2`), which confirms the camera is draw-only
  and perturbs no simulation state. The rotating camera is not the more
  expensive option here; do not read the slice 2 spec 5.3 rejection as a
  measurement of this, since what that rejected was rotating the *finished
  frame*, not the camera transform.

## What the human half needs

Serve it and play it:

    python tools/serve_web.py 8000      # http://localhost:8000

Use `tools/serve_web.py`, **not** pygbag's own dev server. The loader fetches
the archive from a URL with no version in it, and pygbag's server lets the
browser cache it — so you reload and silently play the previous build, with no
error anywhere. Ctrl+Shift+R does not reliably fix it. `serve_web.py` serves
the bundle `no-store` and proxies the runtime, which is why it exists.

**Grey** screen = boot never reached `main.py`; **near-black** = the game is
running.

Controls: **J** or left mouse attracts, **K** or right mouse repels. **Tab**
toggles the HUD overlay, which is where the fps and step numbers are.

Fill in, having played for **at least five minutes actually chaining orbits**
— not booted and looked at:

- [ ] **fps**, from the overlay: `___` (steady-state, not the first seconds)
- [ ] **physics steps per frame**, from the overlay: `___`
      At 60 fps the expected value is 4 (240 Hz sim / 60 Hz frames). A number
      pinned at 12 means `MAX_STEPS_PER_FRAME` is saturating and the
      simulation is running slow motion relative to wall clock, which is the
      specific failure this check exists to catch.
- [ ] **Chaining three orbits feels:** same as native / better / worse
- [ ] **If worse, which:** input latency / frame pacing jitter / physics
      stepping / something else
- [ ] **Does the camera hold up** through a gravity flip, which is new since
      this runbook was first written: `___`
- [ ] **Browser and machine used:** `___`

## Decision

_Pending. One of: same as native / better / worse. If worse, name which of
input latency, frame pacing jitter, or physics stepping._

## Coverage gaps, stated plainly

- One browser on one machine is one data point. Chrome and Firefox schedule
  `requestAnimationFrame` differently and the pygbag runtime sits on top of
  both.
- The headless probe cannot see the browser at all. It measures the same draw
  code compiled for a different target, on different hardware, through a
  different scheduler. It bounds nothing about WASM; it is only the reference
  the browser number gets compared to.
- Nothing here tests input latency directly, which is the failure mode most
  likely to make a chain feel wrong while fps looks fine. It has to be judged
  by hand, which is why this task is a human gate.
- As above: WASM and slice 2 are now confounded. A clean answer would need a
  native run of `f276b10` for comparison.
