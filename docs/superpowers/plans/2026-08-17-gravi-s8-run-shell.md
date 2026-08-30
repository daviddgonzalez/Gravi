# Session S8 — The run shell: scenes, scoring, and the run record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task.

**You are session S8 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**Goal:** Turn "a physics demo you can play" into "a game you start, lose, and start again": a scene layer, real scoring, a persisted best, procedural audio, and — the part everything downstream depends on — a recorded event log per run.

**Blocked on:** S1 merged. Uses `storage.py` from S4 if it has landed; if not, write against a tiny local shim and swap it later rather than duplicating the module.

**Architecture:** A `scenes/` package with an explicit state machine, because the alternative (flags in `main.py`) is how BlueBall got where it got. `main.py` shrinks to: build the scene stack, pump events, tick, draw, `await asyncio.sleep(0)`.

---

## The run event log is the important part of this session

The rival's model of the player (core spec §5.2) is derived from recorded runs: mean orbit radius, release-timing spread, repel frequency, branch preference, reaction latency after a gravity flip, and which archetypes they die in. None of that can be reconstructed after the fact from a score.

So this session commits to a **stable event schema** that session S5 designs statistics over and session S9 consumes. Get it wrong and every recorded run before the fix is useless. Record raw events with timestamps, not derived statistics — deriving is cheap later, un-deriving is impossible.

Minimum event set:

| Event | Fields |
|---|---|
| `run_start` | seed, tunable snapshot, wall clock |
| `chamber_enter` | index, archetype id, entry depth, gravity turns |
| `grab` | t, chamber index, node index, charge, player speed, distance from node centre |
| `release` | t, held duration, exit speed, exit angle relative to gravity |
| `flip` | t, from turns, to turns |
| `death` | t, cause (`core` / `sideways` / `hazard`), chamber index, node index if any |
| `run_end` | distance, chambers cleared, elapsed |

---

## Task 1: the scene layer

**Goal:** Title, run, death and summary as explicit scenes, with `main.py` reduced to a pump.

**Files:** Create `src/gravi/scenes/__init__.py`, `base.py`, `title.py`, `run.py`, `summary.py`; modify `main.py`; test `tests/test_scenes.py`

**Acceptance criteria:**
- [ ] A `Scene` has `handle(event)`, `tick(dt)`, `draw(surface)` and may return a transition
- [ ] Transitions are tested headlessly with no pygame display: title → run → summary → run
- [ ] The tuning overlay and the room editor are still reachable from the run scene (they are how the game gets tuned; losing them costs more than the tidiness gains)
- [ ] `main.py` is under 100 lines and still `await asyncio.sleep(0)` every frame

**Verify:** `PYTHONPATH= SDL_VIDEODRIVER=dummy .venv/bin/pytest tests/test_scenes.py -v` → pass

## Task 2: scoring and the persisted best

**Goal:** Score is distance travelled along the actual path; chambers cleared is the separate difficulty clock; best survives a restart.

**Files:** Create `src/gravi/score.py`; modify `src/gravi/scenes/run.py`, `summary.py`; test `tests/test_score.py`

**Acceptance criteria:**
- [ ] Score is path length, not displacement — a tight orbit that carries speed scores more than a straight fall over the same ground (core spec §3.5); assert exactly that with two scripted runs
- [ ] Chambers cleared is tracked separately and is what any difficulty curve reads from
- [ ] Best distance and best chambers persist through `storage.py` and fail soft in the browser
- [ ] The summary scene shows distance, chambers, best, and the delta against best

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_score.py -v` → pass

## Task 3: the run event log

**Goal:** Every run emits the event stream above, and it round-trips.

**Files:** Create `src/gravi/runlog.py`; modify `src/gravi/sim.py` (emit hooks only — no behaviour change), `src/gravi/scenes/run.py`; test `tests/test_runlog.py`

**Acceptance criteria:**
- [ ] `World` gains an optional `listener` that receives events; with no listener the simulation is byte-identical to before (assert a state trace against a recorded one — this is core spec §9's determinism test, reused)
- [ ] Events serialise to plain JSON and back
- [ ] The log is capped in size and drops oldest-first rather than growing without bound
- [ ] A recorded run replays to the same outcome from its seed and its charge sequence — core spec §9's replay-fidelity requirement, which is what makes the rival, the path map and the difficulty measurements trustworthy
- [ ] Recording costs under 5% of frame time, measured with `tools/perf_probe.py`

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_runlog.py tests/test_sim.py -v` → pass

## Task 4: procedural audio

**Goal:** Sound for grab, release, flip, and death — generated, not authored.

**Files:** Create `src/gravi/audio.py`; port from `~/projects/BlueBall/src/blueball/sfx_gen.py` (86 lines, procedural, no asset files); test `tests/test_audio.py`

**Acceptance criteria:**
- [ ] No audio asset files — everything is synthesised at startup, so nothing has to survive the pygbag packaging step or the MP3 ban documented in `docs/web-build.md`
- [ ] Audio failing to initialise (a real possibility in the browser) disables sound instead of raising
- [ ] Beam pitch tracks force magnitude, so the ear gets the same information the beam thickness carries (§7: the beam is the force)
- [ ] A mute key, and the mute state persists

**Verify:** `PYTHONPATH= SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/pytest tests/test_audio.py -v` → pass

---

## When you are done

Report the event schema as it actually shipped, and tell session S5 directly — their player-model statistics have to be computable from it.
