# Session S5 — Design: the rival, the player model, and what the agent sees

**You are session S5 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**This is a design session. You write one spec and no production code.**

**Goal:** Produce `docs/superpowers/specs/<date>-gravi-slice-5-rival-and-player-model.md` — the design session S9 implements, plus the node-field observation and fitness encoding that session S3 deliberately left as a stub.

**Method:** Use the `superpowers-extended-cc:brainstorming` skill.

**Blocked on:** S1 merged (chamber geometry exists) and S2's difficulty-record schema settled (the rival's brains are measured on the same instrument). Do not start before both.

---

## Why one session designs three things

The observation encoding, the player model, and the rival look separable and are not. The agent's perception vector is what the GA trains against *and* what the rival thinks with *and* the space the player model's statistics have to be comparable in. Design them apart and they will disagree — which is the same class of mistake core spec §8.1 forbids for physics.

---

## The questions that must come back answered

**A. What the agent perceives**

1. The exact observation vector: core spec §8.2 says "relative position, charge, radius and remaining life for the nearest few nodes, plus velocity, gravity direction, and arrow bearing". Fix "few". Fix the ordering rule (nearest-first is the obvious answer and has a known failure mode: the vector's meaning shifts discontinuously when two nodes swap rank — decide whether that matters here).
2. Frames of reference. Gravity rotates, so is the observation in world axes, gravity-relative axes, or chamber-local axes? Gravity-relative is the strong candidate because it makes a chamber's meaning invariant under rotation — which is the same reason the speed clamp moved into those axes in slice 2 §6. Say it explicitly and say what it costs.
3. Normalisation: what scales each component to a comparable range, and what happens when a value exceeds it?
4. How do future entities (hazards, charged surfaces, depleting nodes, a second arrow) enter the vector without invalidating every trained brain? Either reserve the slots now or accept a retrain per entity — both are defensible, but the choice must be deliberate and written down.

**B. Fitness**

5. What is the agent rewarded for? The game's score is distance travelled along the actual path (§3.5), but an agent optimising raw distance will learn to survive rather than to route. Say what the fitness function is and what degenerate strategy each term exists to block.
6. Difficulty measurement asks a different question than training does: §4.3 wants success rate, distinct route count, minimum clearance, and timing-window tolerance. Does the fitness function serve both, or are they separate passes over the same rollout? (S2 owns the measurement schema; you own whether the trained agent's objective is compatible with it.)

**C. The player model**

7. The exact statistics recorded per run. §5.2 names mean orbit radius, release-timing spread, repel frequency, branch preference, reaction latency after a gravity flip, and which archetypes they die in. Define each as computable from the run event log that session S8 records — go read that schema and, if it is missing something you need, say so in the spec so S8 can add it before it is expensive.
8. How many runs does the model average over, and how does it forget? A model that never forgets cannot notice that the player improved.
9. Where does it persist? `storage.py` (session S4) is the mechanism; you decide the payload and its size budget, remembering that the browser has no filesystem.
10. Cold start: what does the rival do on the player's first ever run, before any model exists?

**D. The rival**

11. What are the labelled brain styles, concretely? §5.2 names tight-orbit specialist, wide-and-safe, dead-zone crosser, branch-greedy, node-hog. For each: what training pressure produces it, and how is it verified to actually *be* that style rather than merely labelled one?
12. The matching function: player model → selected/weighted brain. §5.2 says "select and weight the rival whose strengths land on the player's measured weaknesses". Define the metric that makes "lands on their weakness" computable.
13. The aggression dial is exactly three numbers (§5.3): how many anchors it will spend, how far ahead it starts, whether it takes the harder branch. Define ranges, defaults, and what sets them from recent form.
14. Pacing (§5.4): the rival is intermittent — ahead, caught, behind, absent for a chamber or two. What actually drives that? A schedule, a rubber band, or an emergent consequence of it running the same chambers? Emergence is the honest answer only if you can show it produces absence.
15. Node depletion is the rival's entire ability to hurt the player. How does a node's remaining life work numerically, how does the player see it (§7 says brightness is remaining life), and what happens when the rival burns a node the player has already latched onto?
16. Determinism: the rival runs the same chamber chain the player does. Is its trajectory replayable from a seed plus its brain, or is it simulated live? §9's replay-fidelity requirement means the answer has to be "replayable" for the path map to be trustworthy.
17. Identity and persistence: §5.4 says the rival persists across sessions with a name. What is stored, and what does the player see change between sessions?

**E. What is explicitly not in slice 5**

18. Confirm that background fine-tuning of a personal rival against the player's own recorded chamber sequences stays an optional later tier (§5.2), and say what would have to be true to start it.

---

## Constraints you may not design around

- **Live retraining is out.** §5.2 rejects it explicitly: a retrained nemesis is a black box with no difficulty dial, and that was the fatal flaw of the rejected tethered-rival concept. The intelligence lives in the *selection*.
- **The rival never collides with the player** (§5.1). Nothing kills the player except hazards and node cores. Being caught does not kill you. "I know why I died" is what keeps a run-based game honest.
- **It must be perceivable.** §6 makes the path map the perception layer — a rival that learns you is worthless if the player cannot see it. Your design must say what the player sees *during* the run, not only at the end.
- **The browser has no filesystem** and the trainer never runs in it (§8.6). Brains are baked offline and shipped as data.

---

**Acceptance criteria:**
- [ ] Every question A1–E18 answered, or deferred with a named reason and a slice
- [ ] The observation vector appears as a literal, ordered field list with units and normalisation — S3's `env.py` stub is replaced from this list alone
- [ ] The player-model payload appears as a literal schema, cross-checked against S8's run event log
- [ ] A "decisions locked" table and a "rejected alternatives" section exist
- [ ] `git diff --stat main -- src/ main.py` is empty

**Verify:** `git diff --stat main -- src/ main.py` → empty
