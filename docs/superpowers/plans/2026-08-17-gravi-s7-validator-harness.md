# Session S7 — The validator harness and measured difficulty

**You are session S7 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**Blocked on:** S2's parameter-box and difficulty-record schemas (ask for these early — S2 is instructed to emit them before the rest of its spec, precisely so you can start), S3's GA stack, and S1's frozen physics constants.

**First move:** read S2's spec, then run `superpowers-extended-cc:writing-plans` against it to expand this charter into a task plan.

---

## Goal

Turn "solvable" into a number. Build the offline build step that sweeps a template's parameter space, measures difficulty on each validated box, and emits the library the runtime generator asks questions of.

## Scope

**In:**
- `src/gravi/validation/` — the planner sweep (tier 1), the agent gate (tier 2), the measurement pass, and the library writer
- A CLI: `python -m gravi.validation --archetype whip-corridor --samples N --out data/library.json`
- The measurement record per box: agent success rate, count of distinct viable routes, minimum clearance on the best route, input-timing tolerance (core spec §4.3)
- The **invalidation stamp**: a measurement is provably stale after a physics change. Retuning the force law invalidates every measurement (§4.4), and the mechanism must be automatic, not remembered.
- Runtime lookup: the generator asks for "a chamber measured at difficulty 0.62 that accepts a downward entry" and the library answers (§4.3)

**Out:** archetypes themselves (S6), the rival's brains (S9), calibration against human play data (S11 — it needs real play data and cannot be settled before then, §4.4).

## Definition of done

- [ ] The sweep imports `field.py` and `sim.py` directly — never a re-implementation, never a "fast approximation". This is core spec §8.1 and it is the single constraint that makes every number this session produces worth anything.
- [ ] A full validation run over the shipped archetypes finishes inside the time budget S2 set, on the author's machine, with the wall clock printed
- [ ] Re-running with the same seed reproduces the library byte-for-byte
- [ ] Changing `k_attract` and re-running visibly invalidates the previous library rather than silently producing measurements against different physics
- [ ] A box that fails tier 1 never reaches tier 2; the tier-1/tier-2 disposition follows S2's decision on flagging versus discarding
- [ ] The emitted library loads in the browser build — plain JSON or equivalent, no native deps (§8.6)
- [ ] The runtime lookup is covered by a test that asks for a difficulty and asserts it gets a box measured within tolerance of it

## Why this exists at all

Difficulty as a scalar is what makes endless generators boring — "same thing, tighter and faster" exhausts its grammar in a minute (§1.1). Measured difficulty is what lets the generator keep pressure rising while **rotating which knob produces it**, so chamber 40 and chamber 41 are equally hard by different means (§4.3). That is the whole reason the GA stays in this project. If what you build measures only "did the agent survive", it has not done the job.
