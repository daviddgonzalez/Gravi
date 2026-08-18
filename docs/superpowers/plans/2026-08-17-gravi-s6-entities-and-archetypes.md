# Session S6 — Entities and archetypes

**You are session S6 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**Blocked on:** S1 merged (chamber geometry and the chain exist) **and** S2's spec approved (the archetype grammar and parameter-box schema are yours to implement, not to invent).

**First move:** read S2's spec end to end, then run the `superpowers-extended-cc:writing-plans` skill against it to expand this charter into a task-by-task plan at `docs/superpowers/plans/<date>-gravi-s6-tasks.md`. This file is a charter, not that plan — it exists because the detail cannot be written until S2 lands.

---

## Goal

Give the generator something to say. Slice 2 ships one archetype with fixed dimensions; you ship the roster, the entities that make escalation mean something, and the runtime sampling that keeps every chamber novel.

## Scope

**In:**
- The archetype roster from S2's spec, each as its own module under `src/gravi/chambers/`
- Runtime sampling from a validated parameter box
- **Node lifetime and depletion** — nodes deplete when used; brightness is remaining life (core spec §7). This is the mechanic the rival's entire interference model rests on (§5.1), so it must land before S9.
- **Charged surfaces** — the same force law applied to a segment rather than a point: repel off a wall to launch without touching it, attract to slam flat and kill a bad arc (§2.3)
- **Hazards** — placed near bad orbits (§3.6, chambers 4–8)
- **Dead zones** — stretches with no nodes, crossed on inherited momentum only (§3.6, chambers 16–25). Not an entity; a generation constraint. It is also the generator's most important tool, so it is not an afterthought.
- **Branching arrows** — two arrows pointing different ways, the harder line paying more (§3.4). Note the geometric consequence: slice 2 §4.3's "every chamber is entered at offset zero" derivation assumes one exit; redo it for two before writing code.
- The escalation schedule (§3.6) as a data-driven curve over chambers cleared

**Out:** the validator and difficulty measurement (S7), moving/orbiting nodes and overlapping fields (they are the 26+ and 50+ escalation bands — land the roster first), the rival (S9).

## Definition of done

- [ ] Every archetype has a property test over ≥200 seeds asserting its own invariants, plus the two universal ones from slice 2: **no core in the centre lane**, and **an influence ring reaching the lane** in every chamber
- [ ] Depleted nodes are visibly dimmer and stop applying force at zero life, with the transition tested
- [ ] Charged surfaces share `field.py` — if you write a second force law, you have broken core spec §8.1 and every difficulty measurement downstream becomes fiction
- [ ] The escalation curve is data, not `if chamber > 9` branches scattered through the generator
- [ ] The whole roster is deterministic from a seed
- [ ] Frame cost still inside budget with the densest archetype on screen (`tools/perf_probe.py`)

## The trap in this session

Core spec §1 diagnoses BlueBall precisely: twenty entity types that were **additive rather than multiplicative** — adding a cannon did not change what a spike meant. Gravi's roster is five things: node, charged surface, hazard, gravity arrow, rival. If you find yourself adding a sixth because an archetype would be more interesting with it, that is the failure mode reproducing itself. Make the five multiply instead.
