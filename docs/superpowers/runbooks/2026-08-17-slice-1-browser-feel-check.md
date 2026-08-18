# Slice 1 browser feel check

**Date:** 2026-08-17
**Build:** `79fd949` (game code; see *What was tested* below)
**Judged by:** _not yet — awaiting a human at a keyboard_
**Status:** **INCOMPLETE.** The build half is done and recorded. The verdict
half needs someone to play it. Do not cite this runbook as an answer until the
Verdict section is filled in.

Slice 1 was judged playable natively
([verdict](2026-08-11-slice-1-feel-verdict.md)). It left one question open:
does that feel survive WebAssembly frame pacing? This runbook is where that
gets answered, and it is being answered **before** the S1 chamber work merges
— afterwards a bad result no longer says whether WASM or the new code caused
it.

## Decision

_Pending. One of: same as native / better / worse. If worse, name which of
input latency, frame pacing jitter, or physics stepping._

## What was tested

The packaged game is byte-identical to the judged slice 1 build. `79fd949` is
the last commit touching game code; the S4 commits on top of it add
`src/gravi/storage.py`, `tools/`, `.github/` and docs, and nothing in
`main.py` imports any of them:

    git diff --stat 79fd949 HEAD -- main.py src/gravi/ rooms/ presets/ pygbag.ini
     src/gravi/storage.py | 179 ++++++++++++++++++++++++++++++++++++++++++

## Agent-side results

**Build — PASS.**

    $ tools/build_web.sh
    build/web contents:
    -rw-r--r-- favicon.png          18477
    -rw-r--r-- index.html           12122
    -rw-r--r-- s4-ship-layer.apk   179014
    -rw-r--r-- s4-ship-layer.tar.gz 146677

    total size: 356K  (apk: 176K)

`build/web/index.html` exists. The archive is named after the directory
pygbag packaged, not after the project — from a normal `Gravi/` checkout it is
`gravi.apk`. See docs/web-build.md.

**Package contents — PASS.** Unzipped and checked for `main.py`,
`src/gravi/sim.py` and `rooms/slice1.json`: 58 entries, none missing. This
catches the packaging failure that shows up in a browser as a permanently grey
screen.

**Headless frame cost — PASS, native.** Not a browser number, but the baseline
the browser number has to be read against:

| where | mean | p95 | draw | sim |
|---|---|---|---|---|
| dev box (WSL2) | 0.905 ms | 1.889 ms | 0.890 ms | 0.016 ms |
| ubuntu-latest runner | 0.715 ms | 0.923 ms | 0.706 ms | 0.009 ms |

About 5% of a 16.67 ms frame budget natively. The renderer costs fifty times
what the simulation does. If the browser is slower, that ratio says to look at
the draw path first.

## What the human half needs

Serve it and play it:

    tools/build_web.sh --serve      # http://localhost:8000

Reload with **Ctrl+Shift+R**. A normal reload serves the cached archive and
you will be judging the previous build. **Grey** screen = boot never reached
`main.py`; **near-black** = the game is running.

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
- [ ] **Browser and machine used:** `___`

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
