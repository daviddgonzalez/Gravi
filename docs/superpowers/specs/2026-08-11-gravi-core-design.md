# Gravi — Core Design Spec

**Date:** 2026-08-11
**Status:** Approved for planning
**Supersedes:** nothing. This is a new project. BlueBall (`~/projects/BlueBall`) remains untouched; survivors are ported by copy, never by branch or move.

---

## 1. Why this exists

BlueBall reached a state its author described accurately: "we added so many things but nothing holds them together — it's a jumble."

The diagnosis: BlueBall's platforming half was a faithful Red Ball clone with twenty entity types and no hook. The player had no verb that other platformers don't have, and the features were **additive rather than multiplicative** — adding a cannon did not change what a spike meant. Meanwhile the genuinely unusual asset in the repo, a genetic-algorithm (GA) stack that learns levels, sat unused in a side menu.

The reference points that framed the replacement all share one property: a single structural hook that every level is a variation on. Flip gravity (*Run*, *VVVVVV*). Slingshot birds (*Angry Birds*). Two bodies with opposite elements (*Fireboy & Watergirl*). A ball that builds momentum (*Red Ball*). Plus a target *shape*: the continuous flow of *Dune!*, with terrain generated forever and difficulty rising with distance.

Gravi is the result: **one verb, endless escalating terrain, and a rival that learns you.**

### 1.1 The selection test

Four candidate mechanics were developed and stress-tested specifically on their ability to keep an infinite generator interesting. The governing principle:

> Endless generators get boring when difficulty is a **scalar**. If the only escalation knob is "same thing, tighter and faster," the player exhausts the grammar in a minute. Generators stay interesting when difficulty is a **layout**: challenge that varies in kind, carries state across distance, and admits multiple solutions.

| Candidate | Fatal or limiting flaw | Ceiling |
|---|---|---|
| **Mass dial** (one dial changes mass/size) | Terrain resolves to a two-symbol alphabet (heavy/light). Only real knob is tempo. Mastery means the same route executed cleaner. | Low |
| **Spin / Magnus** (only angular input) | Difficulty curve and legibility curve point opposite ways. Every notch of escalation makes the player less able to read their own state. Deaths feel arbitrary. | High in theory, capped by perception |
| **Tethered rival** (elastic tether to the AI) | A GA-trained policy is not a difficulty slider; you cannot reliably train "7 out of 10." Two-body pendulum is chaotic, destroying legible causality. | Unbounded but uncontrollable |
| **Polarity** ← selected | Solvability of generated space must be guaranteed; needs an oracle. | Highest — challenge is a layout, not a dial |

Polarity won because it is the only candidate whose generated challenge is combinatorial (2D node placement, not a linear sequence), whose state carries across distance (momentum enables long-range setups), and where mastery **rewrites what old terrain means** rather than just cleaning up execution.

---

## 2. The core mechanic

### 2.1 The verb

Two inputs, three states: **Attract** (hold), **Repel** (hold), **Neutral** (hold neither). Two triggers or two keys.

There is no jump, no directional movement, and no aim. Both inputs act on **the active node**: the nearest charged node whose influence radius contains the player, drawn with a beam so there is never ambiguity about what is being pulled against. Outside every radius both inputs do nothing and the player is purely ballistic — this is not a dead input, it is the generator's most important tool (see dead zones, §3.6).

### 2.2 The force law

Attract uses a **linear central force**, not inverse-square:

```
attract:  F = k_a · r          toward center,  0 ≤ r ≤ R,  clamped to F_max
repel:    F = k_r · (R − r)    away from center, 0 ≤ r ≤ R, clamped to F_max
outside R: F = 0
```

where `r` is distance from the node center and `R` is the node's influence radius.

Rationale, in priority order:

1. **No singularity.** Inverse-square goes to infinity at the anchor, which is why grapple and orbit games feel twitchy up close and need special-case hacks. A linear force is well-behaved everywhere including `r = 0`.
2. **Every bounded orbit closes.** There are exactly two central-force laws for which bounded orbits reliably close on themselves; this is the one that is not inverse-square. Practically: whatever speed and angle the player grabs at, the result is a clean repeating ellipse rather than a decaying spiral to fight. Predictable is what makes it masterable.
3. **The feel matches the visual.** Force grows with distance, so a far grab yanks hard and a near grab is gentle. It reads exactly like a rubber band stretching, which is what the beam looks like. The player learns the force law without being told it.

Attract and repel are deliberately asymmetric in range profile: **attract is a long-range whip** (strongest at the rim), **repel is a close-range kick** (strongest at contact, fading to nothing at the rim). Two distinct tools from one force system, with no overlap in role.

The beam visibly **snaps** if the player leaves the radius while attracting.

### 2.3 Solid nodes are the entire balance system

A node has a **solid core**. Contact with the core ends the run.

*Tuning fallback if this proves too punishing in slice 1: make death conditional on impact speed above a threshold. Core radius is the primary knob either way.*

This single property does the work that a stamina meter, a cooldown, and a tutorial would otherwise do:

- **It kills the "hold attract forever" degenerate strategy with geometry instead of UI.** Approach a node head-on and hold attract and you die. Approach with lateral offset and the ellipse whips you around the core and out.
- **Approach angle decides whether a node is a slingshot or a wall.** That is the deep skill, and it is continuous and analog rather than binary — not "did you press it" but "how tight did you dare cut it."
- **Tighter orbits exit faster**, so skill opens routes a worse player physically cannot reach. This is the property that lets identical terrain have multiple solutions at different skill levels, which is the only kind of difficulty that never runs out.
- **Repel gets a permanent job**: the emergency out when an approach was misjudged.

Charged **surfaces** obey the same law. Repel off a wall to launch without touching it; attract to a wall to slam flat against it and kill a bad arc.

### 2.4 Gravity

Gravity stays, and it is the engine. The player is always falling, so nodes are always precious and any gap without them is a real threat. It also means a run can never stall, which satisfies the constant-flow requirement through physics rather than a forced-scroll camera.

---

## 3. The run

### 3.1 Chambers and gravity arrows

The world is a connected sequence of **chambers**: pockets of space with a node field, hazards, and one or more **gravity arrows** on the far side. Fly through an arrow and gravity becomes the arrow's direction.

This gives the run a beat — whip between nodes, line up on the arrow, flip, new field, repeat — so it is continuous flow with punctuation rather than an undifferentiated stream.

It also solves the generator's hardest practical problem: **the arrow is the seam.** Every chamber has a known entry vector (the direction gravity now pulls) and a known exit condition, so chambers can be generated independently and stitched with a structural guarantee that they connect.

**Missing an arrow is recoverable, not fatal.** The player keeps falling the old way, now low in the chamber with worse angles. Recovery is possible and is where good players separate.

### 3.2 Why gravity flips work *here* specifically

Gravity flips are normally a legibility disaster because they invert directional controls: "left" still moves you left, but left is now uphill and your jump goes the wrong way.

Gravi has **no directional input**. Attract and repel are defined relative to a node, not relative to the screen. Rotating the world therefore costs nothing in control confusion. This is the one movement system that takes gravity rotation for free, which means the design can be far more aggressive with it than a conventional platformer could.

### 3.3 Camera

On a flip the camera rotates so **gravity is always screen-down**. Fast, eased, roughly 0.2s. Flips are restricted to 90° and 180° increments so every rotation is a clean quarter turn.

The alternative (fixed camera, gravity changes underneath) shows the true layout but makes every arc harder to read, and arc-reading is the entire skill.

**Known risk:** at high flip frequency this will make some players motion-sick. That is a hard cap on one escalation axis, and a fixed-camera accessibility option is required, not optional — some players will prefer it outright.

### 3.4 Branching

A chamber may present **two arrows** pointing different ways. The player chooses; the harder line pays more.

Route choice is rare in endless runners and earns its keep three times over: runs feel authored rather than dealt, skilled players get somewhere to spend confidence, and the generator's output multiplies with no new content. It also gives the rival something meaningful to do (§5.1).

### 3.5 Scoring

**Score is distance travelled along the actual path**, so tight orbits that carry speed genuinely pay. **Chambers cleared** is the separate difficulty clock that the generator reads from.

### 3.6 Escalation schedule

The point of §2 is that these knobs are independent, not one dial. Indicative schedule (final values come from measured difficulty, §4.3):

| Chamber | Knob introduced |
|---|---|
| 1–3 | Node spacing only. Static nodes, generous radii, one arrow, no hazards. |
| 4–8 | Charged surfaces; hazards placed near bad orbits. Approach angle starts to matter. |
| 9–15 | Node lifetime — nodes deplete after use. Route planning begins. |
| 16–25 | Dead zones: stretches with no nodes, crossed on inherited momentum only. |
| 26–35 | Moving and orbiting nodes. Branching arrows appear. |
| 36–50 | Required exit vectors — arrows that accept only a narrow entry angle. |
| 50+ | Overlapping node fields (net force from two anchors), timed auto-flips, moving arrows. |

Only the first row is about spacing; everything after changes what the terrain *means*.

**Overlapping fields are deliberately last.** They hold the richest emergence (figure-eights, compound slingshots) but they break the one-beam-one-anchor clarity the early game depends on, so they are an endgame reward for a player who already reads the system. Until then, the active node is unambiguously the nearest node whose radius contains the player.

---

## 4. Generation and validation

### 4.1 The unit is a template with a parameter box

A chamber is generated from an **archetype** (whip corridor, orbit garden, dead-zone crossing, gauntlet, branch fork) plus sampled parameters: node count, spacing, radii, lifetimes, hazard density, arrow entry tolerance.

**We validate the parameter box, not the individual chamber.** Validating each chamber at runtime means either a frame hitch or a pre-baked library that turns repetitive within a dozen runs. Validating a template across a sampled region of its parameter space, offline, lets runtime jitter freely inside a proven envelope: every chamber the player sees is novel, and every chamber is guaranteed solvable somewhere very close by in parameter space.

### 4.2 Two tiers of validation, both offline

The physics is a point mass under central forces, which is cheap, so headless rollouts are affordable in bulk.

1. **Planner sweep.** For a sampled parameter set, run a randomized trajectory search over attract/repel timing looking for any route from the entry vector to an arrow. Fast, dumb, catches outright impossibility.
2. **Trained agent gate.** An agent from the ported GA stack attempts the same chamber. This catches a different failure class: routes that exist mathematically but demand inhuman precision, or knowledge the player could not have at the moment of entry.

Failing tier 1 → discard. Passing tier 1 but failing tier 2 → discard, or flag high-depth-only.

### 4.3 The AI is the difficulty meter

Solvable is a low bar. The useful output is not a boolean, it is **margin**.

For each validated parameter box, record: agent success rate, count of distinct viable routes, minimum clearance on the best route, and how forgiving the input timing window was. That is a **measured** difficulty rating.

The runtime generator then never asks for "node lifetime on, spacing 320" and hope. It asks for **a chamber measured at difficulty 0.62 that accepts a downward entry**, and the library answers.

Two consequences:

- Difficulty becomes a single tunable curve over chamber count, and every knob feeds it automatically. A new archetype added later needs no rebalancing — it is measured, and it slots itself into the curve.
- **It addresses boredom structurally.** The generator can be instructed to keep difficulty rising while *rotating which knob produces it*, so chamber 40 and chamber 41 are the same measured difficulty arrived at by different means. Steady pressure, constantly changing texture. Very hard to hand-author; nearly free once difficulty is measured.

This is why the GA work stays central — **as an instrument, not as an opponent.** It is what lets an infinite generator be both fair and interesting without a human tuning every knob.

### 4.4 Honest costs

- Offline validation is a build step. It must be reproducible, seeded, and fast enough to re-run whenever physics constants change, because **retuning the force law invalidates every measurement**.
- Measured difficulty is measured *for the agent*, whose weaknesses are not a human's. It needs calibration against real play data or the curve will be wrong in a specific, systematic direction.
- Archetypes are hand-authored. The variety ceiling is set by how many get written. This is ongoing content work the system does not invent for us.

---

## 5. The rival

### 5.1 Physical form: it never touches you

The rival is a second charged body running the same chamber chain. It is solid in the world but **it never collides with the player**. No body-checks, no tether. Its entire ability to hurt the player is this:

**It spends your anchors.**

Nodes deplete when used, and the rival uses nodes. A route planned three chambers ahead can be burned out from under the player by something visibly doing it. This is interference that is fair, readable, anticipatable, and native to the mechanic rather than bolted on. Nodes can be contested by getting there first.

It also competes for branches: take the fork it did not take and the field is clean; follow it and you pick through what it left.

**Being caught does not kill you.** Nothing kills the player except hazards and node cores. Causality stays clean, and "I know why I died" is what keeps a run-based game honest.

### 5.2 What "learns you" means: measurement and selection, not live training

Retraining a nemesis brain live or between runs produces a black box with no difficulty dial. That was the fatal flaw of the rejected tethered-rival concept, and changing the mechanic does not fix it. So:

- **Offline**, breed a population of rival brains with distinct, *labelled* styles — tight-orbit specialist, wide-and-safe, dead-zone crosser, branch-greedy, node-hog — each measured on the same instrument as §4.3, so its strength is known and quantified.
- **At runtime**, build a cheap statistical model of the player from recorded runs: mean orbit radius, release-timing spread, repel frequency, branch preference, reaction latency after a gravity flip, and which archetypes they actually die in.
- **Match**: select and weight the rival whose strengths land on the player's measured weaknesses; set aggression from recent form.

The result reads as "it knows me" because it does, while staying tunable because the intelligence lives in the selection rather than in an opaque training loop. A player who always takes the safe wide arc is matched against a tight-orbit brain that reaches nodes first and burns them.

**Optional later tier**, explicitly not required for the core to work: background fine-tuning of a personal rival against the player's own recorded chamber sequences.

### 5.3 Difficulty dial

Rival aggression is exactly three numbers: how many anchors it will spend, how far ahead it starts, and whether it takes the harder branch. All tunable, none requiring retraining.

### 5.4 Pacing and persistence

Constant on-screen pressure is exhausting and flattens quickly. The rival is **intermittent** — ahead, caught, behind, absent for a chamber or two. Absence is what makes reappearance mean something.

The rival persists across sessions with an identity and a name, and its model of the player updates every run. That is the meta-loop: an endless runner needs a reason to return that is not a number going up, and "it adapted to how I played last night" is a better one than most.

---

## 6. The path map

At the end of a run the camera zooms out and draws the whole route through the chamber chain.

Because the world is a chain of chambers laid out in 2D, **the path is a signature**. This does four jobs at once:

1. Makes the distance score visually honest — the tight orbits that earned it are visible.
2. Produces a shareable image with zero additional art.
3. Gives a personal-best line to overlay on future attempts.
4. **Makes the rival legible.** Its path draws alongside in another colour, showing exactly where it took the other branch and where it got ahead. A rival that learns you is worthless if the player cannot perceive it; this is the perception layer.

Implementation cost is small — sample position every few frames, keep a simplified outline per chamber — but it constrains the architecture: the run must **retain chamber geometry** rather than discarding it behind the camera.

---

## 7. Art direction: neon, functionally

Note: neon was specced for BlueBall but never built (`themes/neon.py` was a placeholder location; only `pixel.py` exists). Gravi builds it fresh, and it works differently here than it would have there.

In BlueBall neon would have been a skin. In Gravi **light is the ruleset**, because everything the player must read is an electrical property:

- **Hue is charge.** Attract-safe nodes, hostile-charge nodes, and hazards each own a hue that appears nowhere else. Colour communicates function before shape can be parsed.
- **The glow ring is the influence radius.** No debug circles, no UI overlay — a node's reach is literally how far its light travels, so the rule and the render are the same object.
- **Brightness is remaining life.** A depleting node dims; when the rival burns an anchor three chambers ahead, the player watches it go dark.
- **The beam is the force.** Thickness and intensity scale with magnitude, so a far grab visibly strains and a near one barely glows.

**Technical payoff:** §8.4 flags that rotating a nearest-neighbour-upscaled pixel surface during a gravity flip will shimmer and crawl. Neon rendered at native resolution with additive glow on a near-black field rotates cleanly. Choosing neon **deletes** that problem rather than solving it. Gravi therefore drops BlueBall's `PIXEL_SCALE` virtual-surface pipeline entirely.

---

## 8. Architecture

### 8.1 The non-negotiable constraint

**The force law is one pure module, and the game, the offline validator, and the trainer all import it.** Not "kept in sync" — the same code.

If the validator simulates physics differing from the game by even a small margin, every difficulty measurement in §4 is fiction, and the generator will confidently emit chambers rated 0.4 that play at 0.9. That failure is invisible until playtesting and maddening to diagnose.

`field.py` owns attract, repel, clamping, and the gravity vector. It imports nothing but physics types. Determinism under a fixed seed is a test, not an aspiration.

This extends a principle BlueBall's `streaming.py` already documented: the trainer must stream the *same* terrain a human sees for a given seed, or the two drift and the agent trains on something the player never plays.

### 8.2 Ported from BlueBall (by copy)

- **`World`** as the headless source of truth. Role unchanged; physics contract changes underneath.
- **The streaming architecture.** `TerrainStream` is shaped correctly already — lazily materialise ahead, cull behind, seeded, shared with the trainer. Chambers replace chunks; gravity arrows replace the linear advance. The content dies, the machine survives.
- **The `ai/` package** as the §4 instrument. `ga.py`, `genome.py`, `trainer.py`, `persistence.py`, `episodes.py`, `metrics.py` carry over nearly intact. `observation.py` and `fitness.py` are **rewritten**: raycasts, ability bits and key bits give way to a node-field encoding (relative position, charge, radius and remaining life for the nearest few nodes, plus velocity, gravity direction, and arrow bearing).
- Scenes, audio, save, and the pytest setup.
- The `Renderer`-as-seam pattern and the theme registry, minus the pixel pipeline.

### 8.3 Not ported

- **The entity roster** — doors, keys, collectibles, pushable boxes, springs, patrollers, one-way and crumbling platforms, falling hazards, boost pads, lava, cannons, chargers, moving platforms, checkpoints, goals, ability pickups. These are pause-mechanics and scripted interactions; a list of twenty obstacles is not a game. Gravi's roster is five things: **node, charged surface, hazard, gravity arrow, rival**.
- **`abilities.py`** — there is one verb; an ability framework is the opposite of this design.
- **`input_feel.py`** — jump buffering and coyote time exist to make a jump button forgiving. There is no jump button.
- **`seams.py`** — solves seam-hop for a fast rolling ball on collinear segments. Nothing rolls.
- **The five hand-built levels and the chunk library** — content for a different game.
- **Rolling physics constants** — torque, angular velocity caps, air control, jump impulse and cut, ground move forces.

### 8.4 New modules

| Module | Responsibility |
|---|---|
| `field.py` | The force law. Pure, dependency-free, shared by game/validator/trainer. |
| `gravity.py` | Gravity vector and flip transitions. |
| `chambers/` | Archetypes and parameterised generation. |
| `validation/` | Planner sweep, agent gate, difficulty measurement; emits the validated template library. |
| `playermodel.py` | Run statistics → player model. |
| `rival.py` | Brain selection/blending and the aggression dial. |
| `pathmap.py` | Path recording and end-of-run rendering. |

### 8.5 Repo

New repo at `~/projects/Gravi`, fresh `git init`. BlueBall stays exactly as-is; survivors are ported by copying modules, not by branching or moving. The point of not reusing the repo is that everything arriving is a deliberate port rather than inherited baggage.

---

## 9. Testing spine

Established from the first commits, because these are what stop §4 from being a house of cards:

1. **Determinism.** Same seed and same input sequence produce an identical state trace.
2. **Force-law purity.** `field.py` imports nothing from pygame, the scene layer, or the renderer — so the validator and the game provably run the same physics.
3. **Replay fidelity.** A recorded run replays to the same outcome. This is what makes the rival, the path map, and the difficulty measurements trustworthy.

---

## 10. Slices

### Slice 1 — Does it feel good? (the only slice that can kill the project)

Everything above rests on one unverified assumption: **whipping around a solid node under a linear central force feels good.** Nothing else matters if that is false.

**In scope:** one hand-placed room; gravity fixed downward; three to five static nodes with solid cores; attract and repel; the beam; death on core impact; instant restart; live-tunable `k_a`, `k_r`, `R`, `F_max`, core radius, and gravity.

**Out of scope:** generation, arrows, rotation, rival, AI, scoring, chambers, art beyond a first neon pass.

**Succeeds if:** three orbits can be chained without deliberation; approach angle visibly decides slingshot-versus-crash; repel feels like a genuine save rather than a panic button.

**Fails if:** after honest tuning the orbits feel floaty, imprecise, or samey. **In that case we do not build a generator on top of it.** Naming this exit now is deliberate.

### Subsequent slices, in order

2. Gravity arrows and camera rotation (plus the fixed-camera accessibility option).
3. Chamber archetypes and streaming.
4. The offline validator and difficulty measurement.
5. The rival and player model.
6. The path map.

---

## 11. Decisions locked

| Decision | Choice | Reason |
|---|---|---|
| Core mechanic | Polarity — attract/repel against charged nodes | Only candidate whose generated challenge is a layout rather than a scalar |
| Inputs | Two (attract, repel); neutral is the third state | Neutral enables ballistic coasting and clean tangential exits |
| Force law | Linear central force, not inverse-square | No singularity; bounded orbits close; visual matches the math |
| Attract/repel profile | Attract strongest at rim; repel strongest at contact | Long-range whip vs close-range kick — two roles, no overlap |
| Balance system | Solid node cores; contact ends the run | Kills the hold-forever strategy geometrically, no meter or UI |
| Active node | Nearest node whose radius contains the player | Legibility; overlapping fields are a deliberate 50+ escalation |
| Gravity | Present, and rotated by gravity arrows | Flow is free from physics; no directional input means rotation is free |
| Camera | Rotates so gravity is always screen-down; 90°/180° only | Arc-reading is the entire skill; fixed-camera option required |
| Missing an arrow | Recoverable, not fatal | Recovery is where good players separate |
| Branching | Two arrows in some chambers, harder line pays more | Route choice multiplies generator output at no content cost |
| Score | Path length travelled; chambers cleared is the difficulty clock | Rewards tight orbits that carry speed |
| Generation unit | Archetype + validated parameter box | Novel every run, provably solvable |
| Validation | Two-tier (planner sweep, then agent gate), offline | No runtime hitch, no unsolvable chambers shipped |
| GA's role | Difficulty **meter**, not opponent | Turns hand-guessed knobs into measured difficulty |
| Rival interference | Depletes nodes; never collides with the player | Fair, readable, anticipatable, native to the mechanic |
| "Learns you" | Player model + offline brain selection | Live retraining is untunable; selection keeps a difficulty dial |
| Art | Neon at native resolution; no pixel pipeline | Light is the ruleset; also deletes the rotation-shimmer problem |
| Repo | New repo at `~/projects/Gravi`; BlueBall untouched | Ports are deliberate, not inherited |

## 12. Open questions

- Whether core contact should be unconditional death or gated on impact speed. Resolved by slice 1 playtesting.
- Calibration method for translating agent-measured difficulty into human-perceived difficulty (§4.4). Needs real play data, so it cannot be settled before slice 4.
- Hue assignments for the charge palette, and whether hostile-charge nodes are a separate entity or a node property.
- Whether the fixed-camera accessibility mode needs a different node-field presentation to stay readable without the rotation cue.
