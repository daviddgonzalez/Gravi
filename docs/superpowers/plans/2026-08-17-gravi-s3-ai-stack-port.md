# Session S3 — Port the GA stack from BlueBall

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task.

**You are session S3 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**Goal:** Bring BlueBall's genetic-algorithm stack into Gravi as `src/gravi/ai/`, running headless against a stub environment, with its tests — so that when session S7 needs a trained agent to gate chamber difficulty, the machinery already exists and works.

**Architecture:** Port by **copy**, never by branch or move — BlueBall stays untouched (core spec §8.5). The GA machinery (`ga.py`, `genome.py`, `ftnn.py`, `trainer.py`, `persistence.py`, `episodes.py`, `metrics.py`) carries over nearly intact; what it *observes* and what it is *rewarded for* do not, and are deliberately out of scope here (see below).

**Tech stack:** Python 3.12 + pytest. The trainer runs natively only and never in the browser (core spec §8.6), so it may use anything in the standard library — but keep it dependency-free anyway, because the fewer moving parts the validator build has, the more often it gets re-run.

**Source:** `~/projects/BlueBall/src/blueball/ai/` — about 1000 lines across eight files. Read `~/projects/BlueBall/src/blueball/ai/trainer.py` and `episodes.py` in full before task 1; they carry the streaming discipline that matters more than the GA itself.

---

## The one thing this session must not do

**Do not port `observation.py` or `fitness.py`.** Core spec §8.2 is explicit that both are *rewritten* rather than ported: BlueBall's raycasts, ability bits and key bits describe a platformer with twenty entity types, and Gravi's agent sees a node field — relative position, charge, radius and remaining life for the nearest few nodes, plus velocity, gravity direction and arrow bearing.

That encoding is **session S5's design work**, because the same encoding has to serve the rival. Your job is to leave a clean seam where it plugs in: an `Observation` protocol and a `Fitness` protocol with a trivial stub implementation good enough to prove the GA loop runs end to end. If you find yourself designing what the agent perceives, you are in the wrong session — stop and report it.

---

## File structure

| File | Origin | Responsibility |
|---|---|---|
| `src/gravi/ai/__init__.py` | new | Package marker + the public surface |
| `src/gravi/ai/genome.py` | port | Flat weight vector + metadata |
| `src/gravi/ai/ftnn.py` | port | The feed-through network the genome parameterises |
| `src/gravi/ai/ga.py` | port | Selection, crossover, mutation |
| `src/gravi/ai/episodes.py` | port | Rollout loop: run one genome against one environment |
| `src/gravi/ai/trainer.py` | port | Generations, populations, checkpointing |
| `src/gravi/ai/persistence.py` | port | Save/load a population; must fail soft (no writable FS in browser) |
| `src/gravi/ai/metrics.py` | port | Per-generation statistics |
| `src/gravi/ai/env.py` | new | The `Environment` / `Observation` / `Fitness` protocols and a stub |
| `tests/test_ai_*.py` | port + new | |

---

## Task 1: package skeleton and the environment seam

**Goal:** Define the interface the GA trains against, so every ported module has something to compile against, and so S5's real encoding is a drop-in.

**Files:**
- Create: `src/gravi/ai/__init__.py`, `src/gravi/ai/env.py`
- Test: `tests/test_ai_env.py`

**Acceptance criteria:**
- [ ] `Environment` protocol: `reset()`, `observe() -> tuple[float, ...]`, `act(action) -> None`, `step() -> None`, `done -> bool`, `outcome() -> dict`
- [ ] The action space is Gravi's, not BlueBall's: **three states** (attract / repel / neutral), expressed as the `Charge` IntEnum from `field.py`, not a bitfield of keys
- [ ] `StubEnvironment` implements the protocol with a trivial scoreable task (e.g. drive a scalar toward a target), enough to prove the GA converges
- [ ] `src/gravi/ai/` imports no pygame

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_ai_env.py tests/test_purity.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_env.py
from gravi.ai.env import StubEnvironment
from gravi.field import Charge


def test_stub_environment_runs_to_done():
    env = StubEnvironment(seed=1)
    env.reset()
    steps = 0
    while not env.done and steps < 1000:
        env.act(Charge.ATTRACT)
        env.step()
        steps += 1
    assert env.done
    assert "score" in env.outcome()


def test_observation_is_a_flat_float_tuple():
    env = StubEnvironment(seed=1)
    env.reset()
    obs = env.observe()
    assert isinstance(obs, tuple)
    assert all(isinstance(v, float) for v in obs)


def test_actions_are_the_three_charges_and_nothing_else():
    env = StubEnvironment(seed=1)
    env.reset()
    for charge in (Charge.ATTRACT, Charge.REPEL, Charge.NEUTRAL):
        env.act(charge)
    with pytest.raises((ValueError, TypeError)):
        env.act(7)
```

Add the purity check for the new package to `tests/test_purity.py`.

- [ ] **Step 2: Run and watch it fail** → `ModuleNotFoundError: No module named 'gravi.ai'`

- [ ] **Step 3: Write `env.py`**

```python
"""What the GA trains against.

BlueBall's agent saw raycasts, ability bits and key bits — a platformer with
twenty entity types. Gravi's agent sees a node field, and there is exactly one
verb with three states. The real encoding (relative position, charge, radius
and remaining life for the nearest few nodes, plus velocity, gravity direction
and arrow bearing) is designed in session S5, because the same encoding has to
serve the rival as well as the difficulty meter. This module is the seam it
plugs into, plus a stub good enough to prove the loop runs.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..field import Charge


@runtime_checkable
class Environment(Protocol):
    done: bool

    def reset(self) -> None: ...
    def observe(self) -> tuple[float, ...]: ...
    def act(self, charge: Charge) -> None: ...
    def step(self) -> None: ...
    def outcome(self) -> dict: ...
```

`StubEnvironment` is a one-dimensional tracking task: an observation of `(position, velocity, target - position)`, attract accelerating one way and repel the other, `done` after N steps, `outcome()` returning the negative integrated error as `score`. Deliberately trivial and deliberately learnable — its only job is to fail loudly if the GA is broken.

- [ ] **Step 4: Run the tests** → all PASS

- [ ] **Step 5: Commit**

```bash
git add src/gravi/ai/ tests/test_ai_env.py tests/test_purity.py
git commit -m "feat(ai): the environment seam the GA trains against"
```

---

## Task 2: port genome, network, and the GA operators

**Goal:** `genome.py`, `ftnn.py` and `ga.py` running in Gravi with their tests, unchanged in behaviour.

**Files:**
- Create: `src/gravi/ai/genome.py`, `src/gravi/ai/ftnn.py`, `src/gravi/ai/ga.py`
- Test: `tests/test_ai_ga.py`

**Acceptance criteria:**
- [ ] Copied from BlueBall by `cp`, then edited — the diff against the original is reviewable and small
- [ ] Every BlueBall-specific import, constant and comment is gone (grep for `blueball`, `jump`, `ability`, `key`, `raycast` — zero hits)
- [ ] Network input and output widths come from the environment, not from a hardcoded platformer observation size
- [ ] Output layer is three-way (attract / repel / neutral), argmax-decoded
- [ ] Seeded runs are reproducible: same seed, same population, byte-identical
- [ ] BlueBall is untouched: `git -C ~/projects/BlueBall status` is clean

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_ai_ga.py -v` → all pass

**Steps:**

- [ ] **Step 1: Copy the originals, commit them verbatim first**

```bash
cp ~/projects/BlueBall/src/blueball/ai/{genome,ftnn,ga}.py src/gravi/ai/
git add src/gravi/ai/{genome,ftnn,ga}.py
git commit -m "chore(ai): copy genome, ftnn and ga from BlueBall verbatim"
```

Committing the verbatim copy first is not ceremony: it makes the next commit a readable diff of *what Gravi changed*, which is the record §8.2 is asking for when it says the port is deliberate.

- [ ] **Step 2: Write the tests that pin the behaviour you want to keep**

```python
def test_same_seed_same_population():
    a = ga.seed_population(size=20, genome_length=48, seed=5)
    b = ga.seed_population(size=20, genome_length=48, seed=5)
    assert [g.weights for g in a] == [g.weights for g in b]


def test_crossover_produces_a_child_of_the_same_length():
    ...


def test_mutation_rate_zero_is_the_identity():
    ...


def test_network_decodes_to_one_of_three_charges():
    net = ftnn.Network.from_genome(genome, inputs=6, hidden=8, outputs=3)
    assert net.decide((0.1, 0.2, 0.3, 0.4, 0.5, 0.6)) in (Charge.ATTRACT, Charge.REPEL, Charge.NEUTRAL)
```

- [ ] **Step 3: Edit the copies until the tests pass** — strip platformer vocabulary, widen the constructor, re-point imports at `gravi`.

- [ ] **Step 4: Run** → all PASS, and `grep -ri blueball src/` → no hits

- [ ] **Step 5: Commit**

```bash
git add src/gravi/ai/ tests/test_ai_ga.py
git commit -m "refactor(ai): retarget the GA at Gravi's three-state action space"
```

---

## Task 3: port episodes, trainer, metrics, persistence

**Goal:** A full training run against `StubEnvironment` converges, checkpoints, and resumes.

**Files:**
- Create: `src/gravi/ai/episodes.py`, `trainer.py`, `metrics.py`, `persistence.py`
- Test: `tests/test_ai_trainer.py`

**Acceptance criteria:**
- [ ] `trainer.run(generations=15, env_factory=StubEnvironment, seed=3)` measurably improves mean fitness from generation 0 to 15
- [ ] A run is fully reproducible from its seed
- [ ] `persistence.save_population` returns `False` instead of raising when the write fails — the same fail-soft contract `room.save_room` already uses, because there is no writable filesystem in the browser (core spec §8.6)
- [ ] `metrics` records per-generation best/mean/worst and the elapsed wall clock
- [ ] The trainer streams the same environment a caller asks for — no hidden global level state. BlueBall's `streaming.py` documented this: the trainer must stream the *same* terrain a human sees for a given seed, or the two drift and the agent trains on something the player never plays.

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_ai_trainer.py -v` → all pass, under 30 s

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
def test_training_improves_on_a_learnable_task():
    result = trainer.run(generations=15, population=24,
                         env_factory=lambda seed: StubEnvironment(seed=seed), seed=3)
    assert result.history[-1].mean > result.history[0].mean
    assert result.best.fitness > result.history[0].best


def test_a_run_is_reproducible_from_its_seed():
    a = trainer.run(generations=5, population=12, env_factory=..., seed=9)
    b = trainer.run(generations=5, population=12, env_factory=..., seed=9)
    assert a.best.genome.weights == b.best.genome.weights


def test_saving_a_population_fails_soft(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.open", _raise_oserror)
    assert persistence.save_population(pop, tmp_path / "x.json") is False
```

- [ ] **Step 2: Copy verbatim, commit, then adapt** — same two-commit discipline as task 2.

- [ ] **Step 3: Run** → all PASS

- [ ] **Step 4: Commit**

```bash
git add src/gravi/ai/ tests/test_ai_trainer.py
git commit -m "feat(ai): headless trainer with reproducible runs and fail-soft persistence"
```

---

## Task 4: a CLI entry point for the trainer

**Goal:** `python -m gravi.ai` trains a population and writes a checkpoint, so S7 can invoke it as a build step without importing internals.

**Files:**
- Create: `src/gravi/ai/__main__.py`
- Test: `tests/test_ai_cli.py`

**Acceptance criteria:**
- [ ] `PYTHONPATH= .venv/bin/python -m gravi.ai --generations 3 --population 8 --seed 1 --out /tmp/pop.json` exits 0 and writes the file
- [ ] `--help` documents every flag
- [ ] Progress prints one line per generation with best/mean fitness, so a long run is legible in a terminal
- [ ] Never imports pygame — the trainer must run on a headless box

**Verify:** `PYTHONPATH= .venv/bin/python -m gravi.ai --generations 3 --population 8 --seed 1 --out "$CLAUDE_JOB_DIR/tmp/pop.json"` → exit 0, file exists

**Steps:**

- [ ] **Step 1: Write the test** — invoke via `subprocess` and assert exit code, file existence, and that the same seed twice produces identical file contents.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Write `__main__.py`** with `argparse`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add src/gravi/ai/__main__.py tests/test_ai_cli.py
git commit -m "feat(ai): a headless training entry point"
```

---

## When you are done

Report: what ported cleanly, what had to be rewritten and why, how long a 15-generation stub run takes (S7 needs that number to budget the validation build), and anything in the BlueBall stack you would not port again.
