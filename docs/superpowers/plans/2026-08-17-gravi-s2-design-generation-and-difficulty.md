# Session S2 — Design: chamber generation and measured difficulty

**You are session S2 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**This is a design session. You write one spec and no production code.** Throwaway probes under `.proto-scratch/` or a scratch HTML prototype are encouraged — the two existing prototypes in `proto/` earned their keep and changed the slice boundary. Nothing in `src/` may change.

**Goal:** Produce `docs/superpowers/specs/<date>-gravi-slices-3-4-generation-and-difficulty.md` — the design that sessions S6 (entities and archetypes) and S7 (validator harness) implement without further design work.

**Method:** Use the `superpowers-extended-cc:brainstorming` skill. Do not write the spec until the questions below are actually settled; a spec that lists options is a deferral, not a design.

**Why this session is on the critical path:** S6 and S7 are both blocked on your output, and slice 4's whole premise — the AI is the difficulty meter, not an opponent — only works if difficulty is a *measured* number with a defined schema. Everything downstream (rival matching, escalation, calibration) reads that number.

---

## What you are designing

Core spec §4 and §3.6 state the intent and stop short of the mechanism. Read both, plus the slice 2 spec (S1 is implementing it now — its `chamber.py` is your starting geometry and its `ChamberParams` is the placeholder your parameter box replaces).

### The questions that must come back answered

**A. The archetype grammar**

1. Which archetypes ship? Core spec §4.1 names five candidates — whip corridor, orbit garden, dead-zone crossing, gauntlet, branch fork. Confirm, cut, or add, and say what each one *teaches* the player. An archetype that does not teach a distinct thing is a re-skin of another one.
2. What is an archetype, concretely — a generator function, a data-driven placement rule set, or a template with holes? This decides how S6 writes them and how many exist a year from now. §4.4 is honest that archetypes are hand-authored and the variety ceiling is however many get written; pick the representation that makes writing the tenth one cheap.
3. How does an archetype declare which entry vectors it accepts and which exit arrows it offers? Branching (§3.4) means two arrows, so the answer cannot assume one.

**B. The parameter box**

4. What is the schema of a parameter box — exact field names and types? S6 samples from it at runtime and S7 measures it offline, and they must not disagree by a single key.
5. Which knobs live in the box, and which are global? Core spec §3.6's escalation table lists node spacing, charged surfaces, hazard density, node lifetime, dead zones, moving nodes, branching, exit tolerance, overlapping fields.
6. How does runtime jitter inside a proven envelope work — uniform sampling within the box, or something shaped? §4.1's promise is "every chamber the player sees is novel, and every chamber is guaranteed solvable somewhere very close by in parameter space". Define "very close by" numerically. This is the load-bearing claim of the whole generation design.

**C. Measured difficulty**

7. What exactly does a difficulty measurement contain? §4.3 names four things: agent success rate, count of distinct viable routes, minimum clearance on the best route, and how forgiving the input timing window was. Define each as a computable quantity — "distinct viable routes" in particular needs a definition of *distinct* that a program can apply.
8. How do those four numbers collapse into the single scalar the runtime asks for ("a chamber measured at difficulty 0.62 that accepts a downward entry")? Weighted sum, a fitted curve, or a lookup — and how is it re-derived when the weights change?
9. What is the library file format the build step emits and the game reads? It ships as a data file (§8.6), must load in the browser, and must be diffable enough that a physics change visibly invalidates it.
10. How does the generator "keep difficulty rising while rotating which knob produces it" (§4.3)? This is the structural answer to boredom, and it needs an actual selection policy, not a sentence.

**D. Validation mechanics**

11. Planner sweep: what search, over what action space, with what budget, and what counts as a route? §4.2 says randomized trajectory search over attract/repel timing. Say how many rollouts, at what timestep, and what the pass threshold is.
12. Agent gate: what does the trained agent have to achieve for a box to pass? Success rate over how many attempts, on how many sampled points inside the box?
13. What happens to a box that passes tier 1 and fails tier 2 — discarded, or flagged high-depth-only? §4.2 leaves this as "discard, or flag". Decide.
14. Reproducibility: how is a measurement stamped so it is provably invalid after a physics change? §4.4 calls retuning the force law "invalidates every measurement" — design the mechanism that makes that automatic rather than remembered. A hash over the force-law constants plus `field.py` source is the obvious candidate; say yes or say better.
15. How long may the full validation build take, and on what hardware? §4.4 says it must be fast enough to re-run whenever physics constants change. Put a number on it — it constrains 11 and 12 directly.

**E. Scope split for the implementing sessions**

16. Which of this is S6 (entities, archetypes, runtime generation) and which is S7 (rollout harness, sweep, measurement, library baking)? Draw the module boundary explicitly, with file names, so the two can run in parallel without colliding.

### Constraints you may not design around

- **The force law is one pure module** and the game, the validator and the trainer all import it (core spec §8.1). Your validator design must call `field.py` and `sim.py`, never a re-implementation, and never a "fast approximation" of them.
- **No new runtime dependencies for the game.** The validator runs natively as a build step and may use whatever it likes; the *library it emits* must load under WebAssembly with pygame-ce and the standard library alone (§8.6).
- **Difficulty is measured for the agent, whose weaknesses are not a human's** (§4.4). Do not design a calibration scheme that pretends otherwise — S11 handles calibration against real play data, and your job is to leave a hook for it.
- **Everything must stay deterministic under a fixed seed** (§9).

---

## Deliverable shape

Follow the house style of the two existing specs: numbered sections, a decisions-locked table, an open-questions section, and — critically — **rejected alternatives recorded with the reason**. Both existing specs are readable a year later precisely because they say what was not chosen and why; the slice 2 spec's §5.2 (two wrong camera answers, both tried) is the model.

**Acceptance criteria:**
- [ ] Every question A1–E16 above has an answer in the spec, or an explicit "deferred to slice N because X"
- [ ] The parameter-box schema and the difficulty-record schema appear as literal field lists that S6 and S7 can implement from without inventing a name
- [ ] The spec names which sessions implement which parts and what each one's first task is
- [ ] A "decisions locked" table and a "rejected alternatives" section exist
- [ ] No production code changed: `git status` shows changes only under `docs/`

**Verify:** `git diff --stat main -- src/ main.py` → empty

---

## Sequencing note

Emit the **parameter-box schema and the difficulty-record schema early** — as soon as they are settled, before the rest of the spec is written — and tell the coordinating session. S7 can start building the rollout harness against those two schemas while you are still writing §D, which is the difference between S7 idling and S7 running in parallel.
