# Gravi — session map

**Date:** 2026-08-17
**Read this first, whichever session you are.** Then read your own plan.

Gravi's remaining work is split across eleven sessions. To start one, tell it:

> You are session S3 of Gravi. Read `docs/superpowers/plans/2026-08-17-gravi-s3-ai-stack-port.md` and execute it.

| # | Session | Plan | Kind | Blocked on |
|---|---|---|---|---|
| S1 | Slice 2: chambers, gravity vector, camera rotation | `2026-08-17-gravi-s1-chambers-and-rotation.md` | build (critical path) | nothing |
| S2 | Design: chamber generation and measured difficulty | `2026-08-17-gravi-s2-design-generation-and-difficulty.md` | **design** | nothing |
| S3 | Port the GA stack from BlueBall | `2026-08-17-gravi-s3-ai-stack-port.md` | grunt | nothing |
| S4 | Ship layer: browser, persistence, CI | `2026-08-17-gravi-s4-ship-layer.md` | grunt | nothing |
| S5 | Design: rival, player model, agent perception | `2026-08-17-gravi-s5-design-rival-and-player-model.md` | **design** | S1, S2's difficulty schema |
| S6 | Entities and archetypes | `2026-08-17-gravi-s6-entities-and-archetypes.md` | grunt | S1, S2 |
| S7 | Validator harness and measured difficulty | `2026-08-17-gravi-s7-validator-harness.md` | grunt | S2's schemas, S3, S1's frozen physics |
| S8 | Run shell: scenes, scoring, run record | `2026-08-17-gravi-s8-run-shell.md` | grunt | S1 |
| S9 | The rival | `2026-08-17-gravi-s9-rival.md` | grunt | S5, S6, S7, S8 |
| S10 | The path map | `2026-08-17-gravi-s10-path-map.md` | grunt | S1 |
| S11 | Calibration, escalation tuning, ship | `2026-08-17-gravi-s11-calibration-and-ship.md` | mixed | S6, S7, S9, S10 |

**Waves.** S1–S4 start now, in parallel, with no file overlap. S5, S6, S7, S8 and S10 start as their blockers clear. S9 then S11 close it out.

S2, S5, S6, S7, S9 and S11 are charters rather than task-by-task plans, because their detail depends on a design that does not exist yet. Each says so and tells you to expand it with the `superpowers-extended-cc:writing-plans` skill once its input spec lands. S1, S3, S4 and S8 are executable as written.

---

## Where the project is

Slice 1 shipped and was judged: `docs/superpowers/runbooks/2026-08-11-slice-1-feel-verdict.md` says PROCEED. There is a playable single room with live tuning, an in-session editor, a neon renderer, and a browser build that boots. Slice 2 is designed (`docs/superpowers/specs/2026-08-13-gravi-slice-2-gravity-and-camera-design.md`) with two working HTML prototypes in `proto/`, and not yet implemented. Slices 3–6 are design-only.

**Read the core design spec** (`docs/superpowers/specs/2026-08-11-gravi-core-design.md`) before touching anything. It is 411 lines and it is the whole game. Its §11 decisions table is what you are implementing; its §12 open questions are what is still genuinely undecided. Nothing else is up for renegotiation mid-session — if your work says a locked decision is wrong, stop and report it rather than routing around it.

---

## House rules

**Commands.** Always prefix with `PYTHONPATH=`:

```bash
PYTHONPATH= .venv/bin/pytest tests/ -v
PYTHONPATH= .venv/bin/python main.py
```

A ROS installation on the author's machine poisons `PYTHONPATH` and pytest dies before collection. This is not optional and it is not a style preference.

**Tests.** TDD: the failing test first, always. The existing suite is the regression net for every session — if your change makes someone else's test fail, you have found a real conflict, not a stale test.

**The three tests that are not negotiable** (core spec §9):
1. **Determinism** — same seed, same input sequence, identical state trace.
2. **Force-law purity** — `field.py` (and now `gravity.py`, `chamber.py`) import nothing from pygame, the scene layer, or the renderer. `tests/test_purity.py` enforces it.
3. **Replay fidelity** — a recorded run replays to the same outcome.

**Dependencies.** The game ships with pygame-ce and nothing else. Every runtime dependency must survive WebAssembly. The offline validator and trainer run natively and may use more, but the *data they emit* must load in the browser. There is no writable filesystem in the browser: anything that saves must fail soft rather than raise.

**The frame loop must `await asyncio.sleep(0)` every frame** or the browser tab locks up. Cheap to keep, painful to retrofit.

**Commits.** Conventional prefixes, present tense, one coherent change each — match the existing log (`git log --oneline`). Commit frequently within a session.

**Branches.** One branch per session, named for it (`s3-ai-stack-port`). Merge to `main` when your definition of done is met and the full suite passes.

**Don't touch other sessions' files.** Each plan states what it owns. If you need a change in a file you do not own, report it rather than making it — a merge conflict in `sim.py` between two sessions costs more than the wait.

---

## Cross-session invariants

These bind more than one session, which is why they live here rather than in any single plan.

**1. One force law.** `field.py` is imported by the game, the offline validator and the trainer — not "kept in sync", the same code (core spec §8.1). If a validator ever simulates physics differing from the game by a small margin, every difficulty measurement is fiction and the generator will confidently emit chambers rated 0.4 that play at 0.9. That failure is invisible until playtesting and maddening to diagnose.

**2. Freeze the physics before baking a library.** Retuning the force law invalidates every measurement (§4.4). S1's playtest may still move `k_attract`, `k_repel`, `force_max`, `gravity` or the speed caps. **S7 must not bake a shipped library until S1 reports the constants final**, and S7's invalidation stamp must make a stale library obvious rather than remembered.

**3. World coordinates never rotate.** Rotation is a draw-time transform only (slice 2 §5.3). Rotating world data would break invariant 1, make saved room JSON meaningless, and force the trail history to rotate too.

**4. The run retains chamber geometry.** The end-of-run path map needs the whole route (§6), so cleared chambers keep a light outline instead of being discarded behind the camera. S1 puts `ChamberChain.outlines` there on its first commit; nobody optimises it away.

**5. Two schemas are contracts between sessions.** S2's parameter-box and difficulty-record schemas bind S6 and S7. S8's run event log binds S5 and S9. Whoever owns a schema publishes it early and announces changes; whoever consumes it does not quietly extend it.

**6. Five entity types, and no sixth.** Node, charged surface, hazard, gravity arrow, rival. BlueBall died of twenty entity types that were additive rather than multiplicative — adding a cannon did not change what a spike meant (§1). A sixth entity needs a spec amendment, not a commit.

---

## Reporting back

End your session with: what shipped, what you had to decide that the spec did not cover, what you left undone, and anything another session needs to know. Name the sessions affected — the coordinating session routes it.
