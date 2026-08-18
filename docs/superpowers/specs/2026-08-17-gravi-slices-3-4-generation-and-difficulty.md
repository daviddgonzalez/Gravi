# Gravi slices 3–4 — chamber generation and measured difficulty

**Date:** 2026-08-17
**Status:** Approved for planning
**Session:** S2 (design). Implemented by S6 (generation) and S7 (validation).
**Reads:** core design spec §3.6, §4, §8; slice 2 spec §4 (chamber geometry).
**Consumed by:** S5 (rival matching), S6, S7, S9, S11 (calibration).

---

## 1. What this decides, and what it does not

Core spec §4 states the intent — a chamber is an archetype plus a validated
parameter box, and the AI measures difficulty rather than playing the villain —
and stops short of every mechanism. This spec supplies the mechanisms, in
enough detail that S6 and S7 write code without inventing a field name.

**It decides:** the archetype roster and what an archetype *is* as a data
structure; the parameter-box schema; the difficulty-record schema; how the four
measured quantities become one scalar; the library file format; the two
validation tiers with their budgets and thresholds; the staleness stamp; and
the module boundary between S6 and S7.

**It does not decide:** how measured agent difficulty maps to *human*
difficulty. That needs real play data and is S11's job (core spec §4.4 says so).
This spec leaves the hook and names it (§4.6).

### 1.1 One constraint arrived during this session

**Flip rate is not a difficulty axis.** The author's direction, 2026-08-17:
difficulty must come from somewhere other than gravity flips until the motion
sickness problem of core spec §3.3 has an answer. Three consequences bind
everything below:

1. Chamber **depth is a global constant, not a sampled knob** (§3.2). Depth is
   the flip-frequency knob — slice 2 measured 1150 at ~26 swaps/min, which
   playtested as unreadable, and 1600 at ~8. Sampling it per chamber would make
   the flip rhythm a generated quantity, which is the opposite of the intent.
2. Flip frequency is **excluded from the escalation knob set** (§3.3). None of
   the knobs that drive the difficulty curve changes how often gravity turns.
3. Core spec §3.6's 50+ band lists **"timed auto-flips"**, whose entire
   mechanism is raising flip frequency. It is flagged here as suspect and
   **gated behind the §3.3 accessibility work** rather than shipped as a
   difficulty axis. See §9.

The remaining knobs from §3.6 — spacing, charged surfaces, hazard density, node
lifetime, dead zones, moving nodes, branching, exit tolerance, overlapping
fields — are more than enough to carry the curve without it.

---

## 2. The archetype grammar

### 2.1 The roster: five, and what each one teaches

Core spec §4.1 names five candidates. Applying its own test — an archetype that
does not teach a distinct thing is a re-skin of another one — the roster ships
as:

| Archetype | Teaches | Structure |
|---|---|---|
| **whip corridor** | Chaining rhythm and carry: release timing is a tempo, not a decision | A staggered line of nodes down the chamber, each reachable only from the previous one's exit arc |
| **orbit garden** | Selection and commitment: which anchor, and how much of it to spend | Sparse, large-radius nodes in open space, several viable orders |
| **dead-zone crossing** | The launch decides the flight: momentum planned before it is needed | One node field, then a span of nothing, crossed ballistically |
| **surface run** | The wall is a tool: repel to launch without touching, attract to slam flat and kill a bad arc | Charged surfaces as the primary anchors, free nodes scarce |
| **branch fork** | Risk assessment under commitment: the choice is positional and irreversible | Two exit arrows tiling the far side, each turning gravity a different way |

**`gauntlet` is cut.** It fails the test: core spec §3.6 already treats hazard
density as a *knob* applied to any archetype at chambers 4–8, so "dense hazards"
is a parameter setting, not a structure. Every chamber a gauntlet would have
produced is reachable as a high-`hazard_density`, low-`node_spacing` box on the
other four. **`surface run` takes its slot**, because charged surfaces are one
of the five entity types (core spec §8.3) and no other archetype makes them the
point rather than the garnish.

Each archetype is a module under `src/gravi/chambers/`, named for it.

### 2.2 What an archetype is, concretely

**A declared parameter box plus a placement program, both data, executed by one
shared interpreter.** Not a bespoke generator function per archetype.

```
Archetype = (
    id:        str,
    free:      tuple[str, ...],       # knob names this archetype ranges over
    fixed:     dict[str, float],      # knob names it pins, and to what
    exits:     int,                   # 1 or 2
    program:   tuple[Rule, ...],      # placement rules, in order
)
```

The `program` is a sequence of rules drawn from a shared vocabulary
(`lane`, `cluster`, `stagger`, `gap`, `surface`, `hazard_near`, `arrow`),
interpreted by `chambers/placement.py`. Writing the tenth archetype is writing
a data literal against a vocabulary that already exists, which is what core spec
§4.4's honest admission — archetypes are hand-authored and set the variety
ceiling — demands we make cheap.

**The escape hatch:** a rule kind may be backed by a small registered function
when the vocabulary genuinely cannot express something. It is a registry entry,
not a per-archetype generator, so the common case stays data and the rare case
stays possible.

**What makes this the load-bearing choice** is not the placement half. It is
that `free` and `fixed` are **declared data**, so the validator can enumerate an
archetype's dimensions without executing it. A generator function that decided
its own knobs at runtime could not be swept.

**Constraint:** `len(free) <= MAX_BOX_DIMS = 6`. Validation cost and box
tightness both scale badly with dimension count (§3.4), so each archetype spends
six dimensions deliberately and pins the rest.

### 2.3 The entry contract, and why "accepts a downward entry" is the wrong question

Core spec §4.3 imagines the runtime asking for *"a chamber measured at
difficulty 0.62 that accepts a downward entry"*. Slice 2 §4.3 makes the
direction half of that question vacuous, and this is worth stating plainly
because it deletes a whole category of bookkeeping.

A chamber is generated in its own frame: origin at the entrance centre, `+d`
into the chamber along gravity, `+perp(d)` across it. Every chamber is entered
at lateral offset **exactly zero**, travelling along `+d`. So in local
coordinates **every chamber is entered downward, always**. No archetype can be
direction-specific, and none declares a direction.

What genuinely varies, and what an archetype therefore *does* declare, is the
**entry envelope**:

- **entry depth** — the offset at which the player crossed the previous arrow
  becomes their depth in this one (slice 2 §4.3). Its range is bounded by the
  *previous* chamber's half-width, so it is a cross-chamber coupling and must be
  checked against the player's actual state at lookup time, not assumed. It may
  be negative: crossing short means starting behind the entrance line.
- **entry speed** — the magnitude of the velocity carried through the arrow.

So the runtime query is `(target difficulty, entry state, exits wanted)`, and
"accepts a downward entry" resolves to "whose entry envelope contains the
player's actual `(depth, speed)`". This is a refinement of §4.3's phrasing, not
a contradiction of it.

### 2.4 The exit contract, and branching geometry

A single-exit archetype declares one arrow spanning the far side, with a `turn`
of ±1 quarter turns (slice 2 §4.2: the arrow *sets* gravity, it does not rotate
it, so crossing is idempotent).

**Two exits tile the far side; they do not sit somewhere in it.** S6's charter
correctly flags that slice 2 §4.3's offset-zero derivation assumes one exit.
Redone for two:

Both arrows lie on the far side, abutting at normalised offset
`branch_split ∈ [-0.6, 0.6]` (in units of half-width). Together they span the
full width, so slice 2's guarantee survives intact — you cross one nearly every
time, and crossing outside *both* means you left sideways, which is still death
and still a real mistake rather than a missed target. The offset-zero derivation
is per-arrow and therefore unchanged: crossing at offset `u` through either
arrow still yields entry depth `±u` and lateral offset zero in the next chamber.

Consequences worth naming:

- **The fork is positional, not a menu.** The player chooses by *where they
  exit*, which means the choice is made by the swing three seconds earlier and
  is irreversible. That is what makes it risk assessment rather than a button.
- **Ties resolve deterministically.** A crossing exactly on the divider goes to
  the lower-index arrow. Determinism (core spec §9) does not tolerate a coin
  flip.
- **Each exit is measured separately** for payout — see `exit_success` in §3.1.
  "The harder line pays more" (§3.4) becomes a computed multiplier rather than
  an authored one.
- Each arrow carries its own `turn`, so the two branches genuinely diverge in
  world space and the path map (§6) shows it.

---

## 3. The parameter box

### 3.1 Schema — `src/gravi/chambers/box.py`

**This file is a contract.** S6 samples from these types at runtime and S7
writes them offline; they must not disagree by a single key. It is pure data,
stdlib only, and it ships in the browser build, so it must stay that way (core
spec §8.6). S7 creates it verbatim as its first task (§6.3).

```python
"""Parameter-box and difficulty schemas: the contract between the runtime
generator (S6) and the offline validator (S7).

Pure data — stdlib only, no pygame, no scipy. This module is imported by the
browser build. tests/test_purity.py enforces it.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Range:
    """A knob's interval inside a box. `step` of 0.0 is continuous; any other
    value quantises to lo + k*step, which is how integer knobs (node_count,
    node_lifetime) are expressed without needing a second type."""

    lo: float
    hi: float
    step: float = 0.0


@dataclass(frozen=True)
class EntryEnvelope:
    """The entry states this box was validated for.

    Direction is absent deliberately. Chambers are generated in local
    coordinates where the entry vector is always +depth (spec 2.3), so no
    archetype is direction-specific. What varies is where along the entrance
    the player arrives and how fast.
    """

    depth_lo: float       # px along +depth; negative means behind the entrance
    depth_hi: float
    speed_lo: float       # px/s, magnitude of entry velocity
    speed_hi: float


@dataclass(frozen=True)
class DifficultyRecord:
    """The four measured quantities of core spec 4.3, plus what it takes to
    trust them.

    The difficulty scalar is deliberately NOT stored. It is computed from these
    by library.score() using weights carried in the library header, so changing
    the weights is a re-score rather than a re-bake (spec 4.2).
    """

    # Core spec 4.3's four, defined computably in spec 4.1.
    agent_success_rate: float      # [0,1] over tier-2 gate attempts
    route_count: int               # distinct route signatures
    min_clearance: float           # px of margin to death on the most forgiving route
    timing_tolerance_ms: float     # largest input jitter surviving at 50%

    # Provenance: what was actually run, so a number can be argued with.
    sweep_success_rate: float        # [0,1] of tier-1 rollouts reaching an exit
    exit_success: tuple[float, ...]  # per-exit tier-1 success rate; len == exits
    trivial: bool                    # a do-nothing rollout clears it
    samples: int                     # Sobol points evaluated
    rollouts: int                    # tier-1 rollouts run


@dataclass(frozen=True)
class ParamBox:
    archetype: str
    box_id: str                    # 16 hex chars; sha256 over archetype+ranges+fixed+stamp
    ranges: dict[str, Range]       # free knobs; at most knobs.MAX_BOX_DIMS
    fixed: dict[str, float]        # knobs pinned for this box
    exits: int                     # 1 or 2
    entry: EntryEnvelope
    cover_radius: float            # measured; see spec 3.4
    texture: dict[str, float]      # escalation knob -> normalised centre; spec 4.5
    tier2: str                     # "passed" | "failed" | "skipped"
    stamp: str                     # physics stamp this was measured under
    measurement: DifficultyRecord

    @property
    def deep_only(self) -> bool:
        """Tier 1 solved it, the trained agent could not. Retained but gated
        (spec 5.4)."""
        return self.tier2 == "failed"
```

### 3.2 The knob registry — `src/gravi/chambers/knobs.py`

One table, because three things read it: archetypes declare which knobs they
use, the validator sweeps them, and the escalation schedule gates them by
chamber band. **A knob that is not in this table cannot be sampled.**

```python
"""The knob registry: every dimension a parameter box may range over.

Global legal ranges live here, not in the archetypes, because normalising a
knob to [0,1] over its global range is what makes cover_radius (spec 3.4) and
texture distance (spec 4.5) comparable across archetypes.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_BOX_DIMS = 6


@dataclass(frozen=True)
class Knob:
    name: str
    lo: float          # global legal range; used to normalise
    hi: float
    step: float        # 0.0 continuous, else quantised
    band: int          # first chamber at which this knob may leave its floor
    floor: float       # the value meaning "off"; knobs sit here before `band`
    escalation: bool   # counts toward texture rotation (spec 4.5)


KNOBS: dict[str, Knob] = {k.name: k for k in (
    #    name                  lo      hi   step  band   floor  escal
    Knob("half_width",      380.0,  700.0,  0.0,    1,  460.0, False),
    Knob("node_count",        2.0,   14.0,  1.0,    1,    4.0,  True),
    Knob("node_spacing",    220.0,  520.0,  0.0,    1,  380.0,  True),
    Knob("node_radius",     150.0,  320.0,  0.0,    1,  240.0,  True),
    Knob("core_radius",      10.0,   34.0,  0.0,    1,   16.0,  True),
    Knob("surface_count",     0.0,    4.0,  1.0,    4,    0.0,  True),
    Knob("surface_length",  200.0,  900.0,  0.0,    4,  400.0, False),
    Knob("hazard_density",    0.0,    2.5,  0.0,    4,    0.0,  True),
    Knob("node_lifetime",     0.0,    4.0,  1.0,    9,    0.0,  True),
    Knob("dead_zone_frac",    0.0,    0.6,  0.0,   16,    0.0,  True),
    Knob("dead_zone_start",   0.1,    0.8,  0.0,   16,    0.4, False),
    Knob("node_drift",        0.0,  140.0,  0.0,   26,    0.0,  True),
    Knob("node_drift_period", 1.5,    6.0,  0.0,   26,    3.0, False),
    Knob("branch_split",     -0.6,    0.6,  0.0,   26,    0.0, False),
    Knob("exit_tolerance",   0.25,    1.0,  0.0,   36,    1.0,  True),
    Knob("overlap",           0.0,    1.0,  1.0,   50,    0.0,  True),
)}
```

Notes on individual knobs:

- `node_lifetime` 0 means infinite; 1–4 is uses before depletion.
- `exit_tolerance` 1.0 is slice 2's full-width arrow; below 1.0 the arrow
  accepts only a centred fraction of the span, which is core spec §3.6's
  "required exit vectors" band.
- `branch_split` is in units of half-width and applies only when `exits == 2`.
- `overlap` 1 permits overlapping influence rings and net force from two
  anchors — the 50+ band, and the only knob that changes what the *active node*
  rule means.
- `half_width` is a knob; **`depth` is not** (§1.1). Constraint:
  `half_width <= depth / 2`, so a wide crossing can never place the player past
  the next chamber's exit. At depth 1600 the ceiling is 800, and the table caps
  it at 700.

**Global constants, identical in every chamber**, living in `config.py`:
`depth`, `lane_clear`, `side_grace`, `entry_clear`, `exit_clear`,
`node_min_gap`, plus all physics constants and `PHYS_DT`. Slice 2's
`ChamberParams` splits along exactly this line: what stays becomes global, what
varies moves into `KNOBS`.

### 3.3 The escalation bands are gates, not a schedule

Core spec §3.6's table becomes the `band` column above plus one curve. A knob
whose band exceeds the current chamber count is pinned to its `floor`, so
chambers 1–3 can only differ in spacing, radius, count and core size, exactly as
§3.6 says. This replaces `if chamber > 9` branches scattered through the
generator with one lookup, which is S6's definition of done.

The **target difficulty curve** `D(n)` over chambers cleared is piecewise-linear
data in `chambers/escalation.py`:

```python
DIFFICULTY_CURVE = (
    (1, 0.05), (3, 0.12), (8, 0.25), (15, 0.38), (25, 0.52),
    (35, 0.65), (50, 0.78), (80, 0.90), (150, 0.97),
)
```

It is asymptotic below 1.0 deliberately: a run should never reach the point
where only the hardest boxes in the library remain, because that is where the
generator runs out of texture to rotate (§4.5).

**Nothing in this curve changes flip frequency** (§1.1).

### 3.4 Runtime jitter, and what "very close by" means numerically

Core spec §4.1's promise — *"every chamber the player sees is novel, and every
chamber is guaranteed solvable somewhere very close by in parameter space"* — is
the load-bearing claim of the whole design, so it gets a number rather than an
adjective.

**Normalisation.** Every knob is normalised to `[0,1]` over its *global* range
from `KNOBS`, not over the box. This makes distances comparable across boxes
and archetypes.

**Box size.** A box is a hyperrectangle of edge `BOX_SPAN = 0.20` in normalised
units in each of its free dimensions, clipped at the global range. Box centres
come from a scrambled Sobol sequence over the archetype's free-knob space,
`BOXES_PER_ARCHETYPE = 40`, giving ~200 boxes across five archetypes.

**Coverage.** Validation evaluates `N_BOX = 32` Sobol points inside the box.
The **covering radius** — the furthest any point in the box can be from the
nearest evaluated point, in normalised L∞ — is then *measured*, not assumed:
4096 uniform samples, each scored against the nearest Sobol point, maximum
taken. It is stored on the box as `cover_radius`. A box with
`cover_radius > COVER_MAX = 0.06` is **split** along its widest free dimension
and both halves re-validated.

The estimate `(BOX_SPAN/2) · N_BOX^(-1/k)` gives 0.056 at k = 6 and 0.042 at
k = 4, so `MAX_BOX_DIMS = 6` and `N_BOX = 32` sit just inside the threshold and
splitting is a fallback rather than a routine cost. The shipped number is the
measured one regardless.

**The claim, stated precisely:**

> Every chamber the runtime generates lies within 0.06 of each knob's global
> range of a specific parameter point that was actually simulated and actually
> solved.

In real units, for `node_spacing` (global range 300 px wide) that is **18 px**.
For `node_radius` (170 px wide), **10 px**. Those are the distances the word
"novel" is buying, and they are small enough that the claim is defensible.

**Runtime sampling is uniform within the box.** Not shaped, not centre-biased.
A box's measurement is an estimate of the difficulty of *the distribution the
runtime will draw from*, and any shaping makes the measurement describe a
distribution nobody plays. Box splitting already provides fine-grained control
where it is wanted.

**Geometric invariants are enforced, never sampled for.** Slice 2's guarantees —
no core within `lane_clear` of the centre lane, an influence ring reaching the
lane, `node_min_gap` between cores, `entry_clear` and `exit_clear` respected —
are applied at placement time by rejection sampling, bounded at
`PLACE_RETRIES = 40`, after which `node_count` is reduced by one and placement
retried. That always terminates, and it means a runtime chamber can never be
geometrically absurd even if the statistical guarantee above were somehow
wrong. The two mechanisms are independent on purpose.

---

## 4. Measured difficulty

### 4.1 The four quantities, defined computably

Core spec §4.3 names four things. Each needs a definition a program can apply.

**1. `agent_success_rate` ∈ [0,1].** Fraction of tier-2 attempts in which a
trained agent reached an exit arrow alive. Measured over `A_POINTS = 8` Sobol
points inside the box × `A_ENTRIES = 4` entry states drawn from the entry
envelope × a **panel of `A_PANEL = 5` distinct genomes** from the trained
population = 160 attempts. The panel exists because one genome's idiosyncratic
blind spot is not a property of the chamber.

**2. `route_count` — and what makes two routes *distinct*.** Every successful
tier-1 rollout produces a trajectory. Reduce it to a **route signature**:

- the ordered sequence of `(node_id, pass_side)` for each latch, where
  consecutive re-grabs of the same node collapse to one entry, and `pass_side`
  is `sign(cross(velocity, offset-to-node))` at closest approach;
- the exit arrow index;
- the exit offset, bucketed into 8 bands across the arrow span.

Two rollouts are the same route iff their signatures are equal. `route_count` is
the number of distinct signatures with at least `ROUTE_MIN_HITS = 3` successful
rollouts, so a fluke is not a route.

Including `pass_side` is deliberate: grabbing the same node clockwise versus
anticlockwise is genuinely a different plan with a different exit vector, and a
signature that ignored it would undercount the thing §4.3 is trying to measure.

**3. `min_clearance` (px).** For each distinct route, take the rollout that
executes it most comfortably — the one whose minimum margin is largest — where
margin at a timestep is
`dist(player, nearest lethal thing) − (core_radius + player_radius)` over all
node cores, hazards and side walls. `min_clearance` recorded on the box is the
**maximum of that over all routes**: how much room the most forgiving line
through the chamber leaves. A small number means every line is tight, which is
the difficulty signal wanted.

**4. `timing_tolerance_ms`.** Take the reference input trace of the most
forgiving route. Jitter each charge *transition* independently by
`uniform(−δ, +δ)` and replay 32 times. Walk a ladder
`δ ∈ {5, 10, 20, 40, 80, 160, 320} ms` and record the largest δ at which at
least half the perturbed replays still succeed. Costs 224 rollouts per box,
negligible against 19,200.

### 4.2 Collapsing to one scalar

Each feature becomes a hardness in `[0,1]`, then a weighted sum:

```
h_success   = clamp01(1 − agent_success_rate)
h_routes    = clamp01((ROUTE_REF − route_count) / (ROUTE_REF − 1))
h_clearance = clamp01(1 − min_clearance / CLEARANCE_REF)
h_timing    = clamp01(1 − timing_tolerance_ms / TIMING_REF)

difficulty  = w_s·h_success + w_r·h_routes + w_c·h_clearance + w_t·h_timing
```

Defaults, carried in the library header, not in code:
`w = (0.50, 0.20, 0.15, 0.15)`, `ROUTE_REF = 6`, `CLEARANCE_REF = 120.0` px,
`TIMING_REF = 200.0` ms.

Success rate dominates because it is the most direct measure of "can this be
done". The other three earn their weight by *distinguishing kinds of hard*: a
box at 0.6 because there is only one route feels nothing like a box at 0.6
because every route passes 15 px from a core, and §4.5's texture rotation needs
to be able to tell them apart.

**How it is re-derived when the weights change: it is not re-derived, it is
re-read.** The scalar is never stored. `DifficultyRecord` holds the four raw
features and `library.score(record, header)` computes the scalar at load time.
Changing weights is a header edit plus a re-score — seconds — not a re-bake.
Only a *physics* change invalidates measurements (§5.5), which is the honest
line between "we changed our minds about what hard means" and "the numbers are
now fiction".

**Weighted sum, not a fitted curve or a lookup.** A fit needs ground truth we
will not have until S11 has human play data, and a lookup table over four
continuous features is a worse-behaved fit with more parameters. When S11 does
have that data it adjusts the calibration curve (§4.6) rather than the weights,
because a monotone remap of one scalar is a thing a human can read and argue
with, and a re-fit of four weights is not.

### 4.3 The library file — `data/library.json`

Plain JSON, `indent=2`, `sort_keys=True`, floats rounded to 6 significant
digits, boxes sorted by `(archetype, box_id)`. It must load under WebAssembly
with the standard library alone (core spec §8.6), and it must be diffable enough
that a physics change is visibly rather than silently a different file — which
the rounding and the stable sort are there to guarantee.

```json
{
  "schema": 1,
  "stamp": "a3f19c02d4e77b18",
  "built": {
    "profile": "default",
    "seed": 20260817,
    "wall_clock_s": 1487.2,
    "boxes": 214,
    "rollouts": 4190976,
    "archetypes": ["branch-fork", "dead-zone-crossing", "orbit-garden",
                   "surface-run", "whip-corridor"]
  },
  "weights": {"success": 0.5, "routes": 0.2, "clearance": 0.15, "timing": 0.15},
  "refs": {"route_ref": 6, "clearance_ref": 120.0, "timing_ref": 200.0},
  "calibration": [[0.0, 0.0], [1.0, 1.0]],
  "boxes": [ /* ParamBox records, as in 3.1 */ ]
}
```

**Trajectories do not ship.** The rollout traces behind every measurement are
written to `data/measurements/<archetype>.jsonl`, gitignored and not packaged,
so the shipped library stays small and diffable while a suspicious number is
still auditable on the machine that produced it.

### 4.4 Rejected library formats

| Format | Why not |
|---|---|
| pickle | Not browser-safe, not diffable, and a format whose contents depend on the class definitions that produced it is the worst possible carrier for a staleness-sensitive artefact |
| msgpack / CBOR | A runtime dependency, for a file read once at load |
| SQLite | No browser story worth having, and a binary diff tells you nothing |
| One JSON file per box | Diffs beautifully, but a few hundred fetches in the browser |

### 4.5 Rising difficulty, rotating texture

Core spec §4.3's structural answer to boredom — *"keep difficulty rising while
rotating which knob produces it"* — needs a selection policy, not a sentence.

Every box carries a **texture vector**: for each `escalation = True` knob, the
box's normalised centre for that knob (its `floor` when the knob is fixed off).
Two boxes with equal difficulty but different texture are equally hard by
different means, which is exactly the pair §4.3 wants to alternate between.

**Selection for chamber `n`:**

1. Compute target `D(n)` from `DIFFICULTY_CURVE`, remapped through the
   calibration curve (§4.6).
2. **Filter** to boxes where: `|score(box) − D(n)| ≤ TOL = 0.05`; the entry
   envelope contains the player's actual `(depth, speed)`; every knob above its
   `floor` has `band <= n`; and `exits` matches what the chain wants. Widen
   `TOL` in steps of 0.05 until the candidate set is non-empty.
3. **Score** each candidate against a recency window of the last `R = 4`
   chambers:
   `pick_score = 1.0·[archetype not among the last R] + L1(texture, mean of recent textures)`.
4. **Take the argmax**, with ties broken by the run's seeded RNG.
5. Sample a point uniformly inside the chosen box (§3.4), place, and push the
   box's archetype and texture onto the recency window.

Call it **difficulty-matched, texture-repelled selection**. Chamber 40 and
chamber 41 come out equally hard and maximally unalike, which is the promise.

Determinism (core spec §9) survives because steps 3–5 consume only the run seed.

### 4.6 The calibration hook for S11

Measured difficulty is measured *for the agent*, whose weaknesses are not a
human's (core spec §4.4). The hook is one field:

`"calibration": [[0.0, 0.0], [1.0, 1.0]]` — piecewise-linear control points
applied to the target difficulty before lookup. It ships as the identity, so it
costs nothing now. S11 replaces the control points from real play data; no
re-bake, no schema change, and the curve stays a thing a human can read.

The **deep-only boxes of §5.4 are the probe**: whether humans clear boxes the
agent could not is the single most informative signal about whether the agent
gate sits in the wrong place, and it arrives free with normal play telemetry.

---

## 5. Validation mechanics

### 5.1 Tier 1 — the planner sweep

**Action space.** `Charge ∈ {ATTRACT, NEUTRAL, REPEL}` per tick. Exhaustive
search is `3^N`, so a rollout is a **randomised piecewise-constant control
schedule**: segment durations log-uniform in `[60 ms, 700 ms]`, each segment's
charge categorical at `attract 0.45 / neutral 0.35 / repel 0.20`. The bias
toward attract reflects that attract is the whip and the primary tool; neutral
is second because ballistic coasting is how dead zones are crossed.

**Timestep.** `PHYS_DT`, i.e. 240 Hz, via `sim.World` — the game's, unmodified.
Not a coarser step "for speed". Core spec §8.1 does not have an efficiency
exemption, and a validator running 120 Hz physics would produce measurements
that are fiction in exactly the way §8.1 warns about.

**Budget.** `SWEEP_ROLLOUTS = 600` per Sobol point, `N_BOX = 32` points, with
early exit once `ROUTE_TARGET = 12` successes are found at a point — enough to
count distinct routes without paying for the rest. Each rollout is capped at
`MAX_SIM_SECONDS = 12` of game time.

**What counts as a route.** A rollout succeeds iff the player crosses an exit
arrow inside its accepted span while alive. Leaving sideways, hitting a core or
a hazard, and exceeding the time cap are all failures.

**Pass threshold.** A box passes tier 1 iff **every one of its 32 Sobol points
yields at least `MIN_SUCCESSES = 3` successful rollouts.** One unsolvable point
means the box contains unsolvable terrain, and since the runtime samples the box
uniformly, that is a box which will eventually kill a player through no fault of
theirs.

**Triviality pre-filter.** Before the 600, run two rollouts: all-neutral, and
all-attract. If all-neutral succeeds, the chamber is cleared by doing nothing;
set `trivial = true`. Trivial boxes are not discarded — chambers 1–3 need
somewhere gentle to start — but they are excluded from selection above chamber
`TRIVIAL_MAX_CHAMBER = 5`.

### 5.2 Box splitting

A box that fails tier 1, or whose measured `cover_radius` exceeds `COVER_MAX`,
is **split** along its widest free dimension into two halves, each re-validated
independently, to `MAX_SPLIT_DEPTH = 3`. A box still failing at depth 3 is
discarded and logged with the failing point.

Splitting is what turns a sloppy region into several tight, honest ones, and it
serves §3.4's coverage requirement with the same machinery. It also means a
mostly-good region is not thrown away because one corner of it is impossible.

### 5.3 Tier 2 — the agent gate

Attempts as defined in §4.1(1): 8 points × 4 entry states × a 5-genome panel =
160. **A box passes iff `agent_success_rate >= AGENT_GATE = 0.15`.**

The gate is deliberately low. Its job is to catch the failure class core spec
§4.2 names — routes that exist mathematically but demand inhuman precision, or
knowledge the player could not have at the moment of entry — not to reject hard
chambers. A box the agent clears 20% of the time is a *good hard chamber*, and
the measured rate is what carries that into the difficulty scalar. Setting the
gate high would silently truncate the top of the curve.

The gate reuses 8 of tier 1's 32 Sobol points rather than drawing fresh ones, so
the two tiers' numbers describe the same terrain and can be compared directly.

### 5.4 Tier 1 pass, tier 2 fail: the deep-only tier

Core spec §4.2 leaves this as "discard, or flag high-depth-only". **Decision:
retain, flagged.**

Such a box is kept with `tier2 = "failed"`. Its `agent_success_rate` is whatever
was measured (typically 0.0), so `score()` returns a value, but the box is
**excluded from ordinary selection**. It may be drawn only when all of:

- chamber count `>= DEEP_ONLY_CHAMBER = 60`;
- at most 1 chamber in 5 is deep-only (tracked in the recency window);
- tier 1 found `route_count >= 1` and `min_clearance > 0` — there is a real line
  through it with real margin, it is just not one the agent found.

**Why retain rather than discard.** Discarding caps the hardest terrain the
generator can express at the skill of whatever the GA happened to reach, which
makes the endgame systematically easier than it should be for a strong human —
and does so invisibly. Retaining also turns the flag into the S11 calibration
probe of §4.6, which is the difference between hedging and gaining information.

### 5.5 The physics stamp

Core spec §4.4: retuning the force law invalidates every measurement. The
mechanism must be automatic, not remembered.

The charter proposes a hash over the force-law constants plus `field.py`.
**Broader, because the constants alone are not the whole input to a rollout:**

```
stamp = sha256(canonical_json({
    "schema": SCHEMA_VERSION,
    "sources": {path: sha256(file bytes) for path in (
        "src/gravi/field.py",
        "src/gravi/sim.py",
        "src/gravi/chamber.py",
        "src/gravi/chambers/**/*.py",
    )},
    "constants": {
        "k_attract", "k_repel", "force_max", "gravity",
        "speed_max", "fall_speed_max", "player_radius", "PHYS_DT",
    },   # values as used for the bake
}))[:16]
```

`chambers/` is included because changing an archetype's placement changes the
chamber, not merely the physics acting on it, and a measurement of a chamber
that no longer exists is exactly as false as one taken under different gravity.

**Raw file bytes, not a comment-stripped AST.** A comment edit therefore
invalidates the library. That is a deliberate acceptance of false positives: a
spurious 25-minute rebuild is cheap, and a missed invalidation is the failure
core spec §8.1 calls invisible until playtesting and maddening to diagnose. The
risk asymmetry is not close.

**Enforcement is a test, not a convention.** `tests/test_library_stamp.py`
recomputes the stamp and asserts it equals `library.json`'s header. A physics
tweak turns the suite red on the next run, which is what "automatic rather than
remembered" has to mean.

### 5.6 The build budget

**Full rebuild: under 30 minutes wall clock on 14 cores. Single archetype: under
5 minutes.** Every count in this section is set backwards from that:

| | count | rollouts |
|---|---|---|
| boxes | ~214 (5 archetypes × 40, plus splits) | |
| tier 1 | 32 points × 600 | 19,200 / box |
| timing ladder | 7 × 32 | 224 / box |
| tier 2 | 8 × 4 × 5 | 160 / box |
| **total** | | **~4.2M rollouts** |

At ~3.5 ms per headless rollout (≈1,200 steps at 240 Hz, pure Python) that is
roughly 4 CPU-hours, ≈ 18 minutes across 14 cores, plus the agent gate's more
expensive per-step network evaluation. It fits, with headroom for the estimate
being wrong by a third.

Every one of these numbers lives in **`validation/budget.py` and nowhere else**,
so tightening the budget is a single edit, and a `--profile thorough` variant
can raise them all for a final pre-ship bake. The profile name is recorded in
the library header, because a library built at one profile and compared against
another is a trap.

### 5.7 Determinism under parallelism

Rollouts are distributed across processes, so a shared RNG stream would make the
build non-reproducible — and core spec §9 makes determinism a test, not an
aspiration.

**Every rollout seeds from `(run_seed, box_id, point_index, rollout_index)` and
draws from its own generator.** No worker shares state, results are re-ordered
deterministically by index on collection, and `-j 1` and `-j 14` produce
byte-identical libraries. S7's definition of done already requires byte-for-byte
reproduction; this is the mechanism that delivers it.

---

## 6. Scope split: S6 and S7

### 6.1 Module map and ownership

**S6 owns `src/gravi/chambers/` except the two contract files:**

| File | Responsibility |
|---|---|
| `chambers/archetype.py` | The `Archetype` dataclass, the placement-rule vocabulary, the registry |
| `chambers/placement.py` | The one shared interpreter turning a program + sampled knobs into entities |
| `chambers/whip_corridor.py` | Archetype data |
| `chambers/orbit_garden.py` | Archetype data |
| `chambers/dead_zone.py` | Archetype data |
| `chambers/surface_run.py` | Archetype data |
| `chambers/branch_fork.py` | Archetype data; the two-arrow geometry of §2.4 |
| `chambers/entities.py` | Hazards, charged surfaces, node lifetime and depletion |
| `chambers/generate.py` | Runtime: sample a point in a box, place, return a `Chamber` |
| `chambers/escalation.py` | `DIFFICULTY_CURVE`, band gating, the §4.5 selection policy |
| `chambers/library.py` | **Load and query only.** Ships in the browser build |

**S7 owns `src/gravi/validation/` entirely, plus the two contract files:**

| File | Responsibility |
|---|---|
| `chambers/box.py` | §3.1 schemas — **contract**, created by S7, imported by both |
| `chambers/knobs.py` | §3.2 registry — **contract**, created by S7, imported by both |
| `validation/budget.py` | Every count and threshold in §5 |
| `validation/stamp.py` | §5.5 |
| `validation/boxes.py` | Sobol box centres, splitting, `cover_radius` |
| `validation/sweep.py` | Tier 1 |
| `validation/gate.py` | Tier 2; the only file importing `gravi.ai` |
| `validation/measure.py` | Route signatures, clearance, the timing ladder |
| `validation/writer.py` | Builds and writes `data/library.json` |
| `validation/__main__.py` | The CLI |

**Two rules that keep the boundary real:**

1. **`chambers/` never imports `validation/`.** The validator is a native build
   step; the runtime is a browser build. `tests/test_purity.py` gains a case
   asserting that `gravi.chambers.*` imports nothing from `gravi.validation` and
   nothing outside the standard library and `gravi`. The validator may use
   whatever it likes — `scipy.stats.qmc.Sobol` in particular — precisely because
   that test makes the leak impossible to ship by accident.
2. **The schemas live on the runtime side.** `box.py` and `knobs.py` sit in
   `chambers/` even though S7 writes them first, because the game must read a
   box without dragging the validator into the WebAssembly bundle.

### 6.2 Why S7 writes the contract files

S7 is unblocked before S6 is — S6 waits on S1's merge, S7 waits only on S3 and
frozen physics — and S7 needs the schemas on day one. The literal source in
§3.1 and §3.2 is complete enough to type in verbatim, so there is nothing left
to decide and no way for the two sessions to diverge.

### 6.3 First tasks

**S6's first task:** `chambers/archetype.py` and `chambers/placement.py` with
`whip_corridor` as the only archetype, and a property test over 200 seeds
asserting slice 2's two universal invariants — no core in the centre lane, and
an influence ring reaching the lane — for every sampled point in a hand-written
box. Roster, entities and escalation come after the interpreter is proven on one
archetype.

**S7's first task:** create `chambers/box.py` and `chambers/knobs.py` verbatim
from §3.1 and §3.2, plus `validation/stamp.py` and
`tests/test_library_stamp.py`. The stamp lands first, before any measurement
exists, so there is never a window in which a library could be baked without
one.

### 6.4 What this spec asks of other sessions

- **S1** — needs to hear §1.1 directly; it is the only session running in
  parallel that this affects. Chamber depth stays a global constant and should
  default to the readable value (1600, ~8 swaps/min, not the prototype's 1150 at
  ~26). Flip duration and the fixed-camera option are judged on readability, not
  on making flips a challenge.
- **S1 → S6 handoff** — `field.py` gains `Surface` and `surface_force()` for
  §2.1's surface-run archetype. S6 needs it; S1 owns `field.py` through slice 2.
  The edit lands **after** S1 merges, by S6, and it must be the same force law
  applied to a segment rather than a second law (core spec §8.1).
- **S5** — the difficulty schema it is blocked on is §3.1 and §4.2. Note that
  the scalar is computed, not stored, so rival matching reads
  `library.score(box, header)` rather than reading a field.
- **S11** — the calibration hook is §4.6 and the deep-only boxes of §5.4 are the
  probe. Neither requires a re-bake.

---

## 7. Decisions locked

| Decision | Choice | Reason |
|---|---|---|
| Archetype roster | whip corridor, orbit garden, dead-zone crossing, **surface run**, branch fork | Each teaches a distinct thing; gauntlet did not |
| Gauntlet | Cut; becomes `hazard_density` + spacing knobs | §3.6 already makes hazards a knob, so it was a re-skin |
| Archetype representation | Declared knob set + data placement program, one shared interpreter | Makes the tenth archetype a data literal, and lets the validator enumerate dimensions without executing anything |
| Box dimensionality | `MAX_BOX_DIMS = 6` | Coverage and validation cost both degrade fast beyond it |
| Entry declaration | Entry *envelope* (depth, speed); no direction | Local coordinates make every chamber downward-entered; direction is vacuous |
| Branch geometry | Two arrows tiling the full far side, abutting at `branch_split` | Preserves slice 2's "you cross one every time"; makes the choice positional |
| Chamber depth | Global constant, not a knob | Flip rate is not a difficulty axis (§1.1) |
| Chamber half-width | Per-box knob, capped at `depth/2` | Varies chamber character without touching tempo |
| Runtime sampling | Uniform inside the box | Any shaping measures a distribution nobody plays |
| "Very close by" | ≤ 0.06 of each knob's global range, measured per box as `cover_radius` | Gives the load-bearing claim a number: 18 px on spacing |
| Geometric invariants | Enforced by rejection at placement, not validated statistically | Independent of the statistical guarantee, so both must fail to ship a bad chamber |
| Distinct route | Ordered `(node_id, pass_side)` latch sequence + exit + offset bucket, ≥3 hits | Computable, and orbit direction is genuinely a different plan |
| Difficulty scalar | Weighted sum of four normalised hardnesses | A fit needs ground truth that does not exist until S11 |
| Scalar storage | **Not stored** — computed at load from header weights | Re-weighting is a re-score, not a re-bake |
| Library format | One `data/library.json`, sorted, rounded, stdlib-loadable | Browser-safe and diffable; trajectories stay off-ship |
| Tier-1 threshold | ≥3 successes at **every** Sobol point | Uniform runtime sampling means one bad point is a real death |
| Tier-2 gate | `agent_success_rate >= 0.15` | Catches "no route the agent can find" without truncating the top of the curve |
| Tier-1 pass / tier-2 fail | Retained, `deep_only`, chamber ≥60 and ≤1 in 5 | Discarding caps difficulty at the GA's skill, invisibly; retaining also feeds S11 |
| Staleness stamp | sha256 over `field/sim/chamber/chambers` **raw bytes** + physics constants | A spurious rebuild is cheap; a missed invalidation is the §8.1 failure |
| Stamp enforcement | A test that fails the suite | "Automatic, not remembered" has to mean this |
| Build budget | <30 min full on 14 cores; all counts in `budget.py` | Fast enough to re-run whenever physics moves (§4.4) |
| Sweep determinism | Per-rollout seed from `(run_seed, box_id, point, index)` | `-j 1` and `-j 14` must produce identical libraries |
| Selection policy | Difficulty-matched, texture-repelled, recency window 4 | The structural answer to boredom, as an algorithm |
| Schema ownership | `chambers/box.py`, `chambers/knobs.py` written by S7, imported by both | S7 is unblocked first; the runtime must not import the validator |

---

## 8. Rejected alternatives

**Per-archetype generator functions.** The obvious approach, and it makes the
first archetype fastest to write. Rejected because the validator must enumerate
an archetype's knobs without running it, and because §4.4 is explicit that
archetypes are ongoing content work — the cost that matters is the tenth one,
not the first.

**Fully data-driven placement with no escape hatch.** Rejected in the other
direction: the vocabulary needed to express dead-zone placement and two-arrow
geometry purely declaratively becomes a mini-language, and debugging a
mini-language nobody else uses is worse than a registered function.

**Per-chamber sampled depth.** Rejected twice over. It makes flip rhythm a
generated quantity, which §1.1 forbids outright; and it makes measurements
incomparable, because the same `node_spacing` means something different in a
2200-deep chamber than in a 1200-deep one.

**Centre-biased (beta) sampling inside a box.** Attractive because runtime
chambers would cluster near the best-validated region. Rejected because the box
measurement then describes a distribution the runtime does not draw from, so the
number shipped is not the number played. Splitting boxes gives the same control
honestly.

**Validating individual chambers instead of boxes.** This is core spec §4.1's
own rejection and it stands: per-chamber validation at runtime is a frame hitch,
and a pre-baked chamber library turns repetitive within a dozen runs.

**Storing the difficulty scalar in each record.** Simpler to read, and it is
what the first draft of this spec did. Rejected because re-weighting would then
require re-baking, which quietly couples "we changed our minds about what hard
means" to a 25-minute build — and a coupling like that is how weights stop
getting tuned.

**Hashing a comment-stripped AST for the stamp.** Avoids spurious rebuilds on a
docstring edit. Rejected on risk asymmetry: it is more code, it has more ways to
be subtly wrong, and the failure mode it introduces — a real change that does
not invalidate — is precisely the one core spec §8.1 describes as invisible
until playtesting.

**A coarser validator timestep.** The single most effective way to fit the build
budget, and forbidden. Core spec §8.1 has no efficiency exemption; a validator
running different physics from the game produces measurements that are fiction.
The budget was set around 240 Hz instead.

**Discarding tier-2 failures.** See §5.4. Rejected because the cap it imposes on
top-end difficulty is both real and invisible.

**Splitting the roster into more, smaller archetypes.** Tempting, because more
archetypes means more variety for free. Rejected for now: each one costs a slice
of the 30-minute validation budget and hand-authored placement, and five that
each teach something beats eight where three are re-skins. This is the BlueBall
failure (core spec §1) in its generator-shaped form.

---

## 9. Open questions

- **`timed auto-flips` in core spec §3.6's 50+ band.** Its mechanism is raising
  flip frequency, which §1.1 removes from the difficulty knobs. It is not in
  `KNOBS`. Either it is cut from the escalation table, or it returns once §3.3's
  motion-sickness question has an answer. **Needs a decision before S11 tunes
  the endgame**, not before S6 starts.
- **Calibration.** Core spec §12 already lists it; §4.6 here is the hook, not
  the answer. S11, with real play data.
- **`AGENT_GATE = 0.15`.** Set by judgement, not measurement. The first real
  bake will show the distribution of `agent_success_rate` across boxes, and the
  gate should be revisited against that histogram — it is a constant in
  `budget.py` and not in the library header precisely so it can move cheaply.
- **Panel composition.** Five genomes from the trained population, but *which*
  five — top-5 by fitness, or 5 spread across the §5.2 style labels the rival
  work needs anyway? S5 designs those labels; if they land before S7 bakes,
  spread beats top-5, because a panel of near-identical champions measures one
  strategy.
- **Whether `room.py` survives.** Inherited from slice 2's open questions. The
  editor is genuinely useful for authoring an archetype's placement program by
  hand and reading off the numbers, which argues for keeping it. S6 decides.
- **Surface force law.** `surface_force()` is asserted here to be the same law
  applied to a segment (nearest point on the segment, then §2.2's profiles). It
  has not been prototyped, and whether attract-to-a-wall feels like "slam flat"
  rather than "stick" is a feel question of the kind slice 1 answered with a
  build. **S6 should prototype it before writing `surface_run`.**

---

## Appendix A — where the S2 charter's questions are answered

The charter (`2026-08-17-gravi-s2-design-generation-and-difficulty.md`) poses
sixteen questions. None is deferred.

| | Question | Answered in |
|---|---|---|
| A1 | Which archetypes ship, and what each teaches | §2.1 |
| A2 | What an archetype is concretely | §2.2 |
| A3 | How entry vectors and exit arrows are declared | §2.3, §2.4 |
| B4 | Parameter-box schema, exact fields and types | §3.1 |
| B5 | Which knobs are per-box, which global | §3.2 |
| B6 | Runtime jitter, and "very close by" as a number | §3.4 |
| C7 | The four measured quantities, computably | §4.1 |
| C8 | Collapsing them to one scalar, and re-deriving it | §4.2 |
| C9 | The library file format | §4.3, §4.4 |
| C10 | Rising difficulty, rotating knob — the selection policy | §4.5 |
| D11 | Planner sweep: search, action space, budget, route | §5.1 |
| D12 | Agent gate thresholds | §5.3 |
| D13 | Tier-1 pass, tier-2 fail: discard or flag | §5.4 |
| D14 | The invalidation stamp | §5.5 |
| D15 | Build time budget and hardware | §5.6 |
| E16 | S6 / S7 module boundary and first tasks | §6 |
