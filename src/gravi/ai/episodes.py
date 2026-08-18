"""Rolling one genome out against one environment, and scoring it across many.

Most of BlueBall's `episodes.py` was level, gym and ability machinery and did
not come across. What did is the part worth keeping: **a genome is scored on a
list of episodes, not one**, and the per-episode scores are aggregated in a way
that punishes inconsistency.

That matters more for Gravi than it did for BlueBall. S7 uses a trained agent
to measure how hard a chamber is, and an agent that clears seed 4 brilliantly
and seed 5 not at all produces a difficulty number that is noise. Selecting on
`mean - lam*std` (or on the worst episode outright) is what buys an agent whose
score means something across chambers rather than on the one it memorised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from .env import Environment, score_of
from .ftnn import FTNN, Shape

__all__ = [
    "EpisodeSpec",
    "aggregate_fitness",
    "generate_seeds",
    "rollout",
    "evaluate_genome",
]

#: Builds the environment for one episode seed. The caller supplies this, which
#: is the whole point: the trainer never reaches for a level of its own, so it
#: cannot drift from the chambers a player actually sees.
EnvFactory = Callable[[int], Environment]


@dataclass(frozen=True)
class EpisodeSpec:
    """One evaluation episode. Frozen and picklable, so it survives a
    multiprocessing.Pool."""

    seed: int
    max_steps: int = 10_000
    #: Divisor applied to this episode's raw fitness. Lets episodes of
    #: different natural scale be compared without the biggest one dominating
    #: selection.
    norm: float = 1.0


def aggregate_fitness(scores: Sequence[float], lam: float, mode: str = "mean_std") -> float:
    """Combine per-episode fitnesses into one selection score.

    mode="mean_std": mean - lam*std (population std, ddof=0) — the default.
    mode="min":      min(scores) — the worst-case objective; lam is ignored.
                     Forces selection to raise the weakest episode's score.

    For a single score both modes return that score exactly (population std is
    0), so single-episode training is numerically identical to no aggregation
    at all. Empty input is a programming error.
    """
    arr = np.asarray(scores, dtype=np.float64)
    if arr.size == 0:
        raise ValueError("aggregate_fitness requires at least one score")
    if mode == "min":
        return float(arr.min())
    if mode == "mean_std":
        return float(arr.mean() - lam * arr.std())
    raise ValueError(f"unknown aggregate mode {mode!r}")


def generate_seeds(base: int, n: int) -> list[int]:
    """`n` distinct episode seeds derived deterministically from `base`.

    The base seed is always first, so a multi-seed run still includes the
    reference course.
    """
    if n <= 1:
        return [int(base)]
    rng = np.random.default_rng(int(base))
    seeds = [int(base)]
    while len(seeds) < n:
        s = int(rng.integers(0, 2**31))
        if s not in seeds:
            seeds.append(s)
    return seeds


def rollout(net: FTNN, env: Environment, max_steps: int) -> dict:
    """Drive `env` with `net` until it is done or `max_steps` elapse.

    Returns the environment's own outcome dict, with `steps` overwritten by
    what actually ran, so a truncated episode is distinguishable from a
    completed one.
    """
    env.reset()
    steps = 0
    while not env.done and steps < max_steps:
        env.act(net.decide(env.observe()))
        env.step()
        steps += 1
    outcome = dict(env.outcome())
    outcome["steps"] = steps
    outcome["truncated"] = not env.done
    return outcome


def evaluate_genome(
    genome: np.ndarray,
    shape: Shape,
    episodes: Sequence[EpisodeSpec],
    env_factory: EnvFactory,
    *,
    fitness=score_of,
    lam: float = 0.0,
    mode: str = "mean_std",
) -> float:
    """Score one genome across every episode and aggregate.

    A fresh environment per episode, built by the caller's factory from the
    episode seed — no state survives from one episode to the next, which is
    what makes a genome's score a property of the genome.
    """
    if not episodes:
        raise ValueError("evaluate_genome requires at least one episode")
    net = FTNN(genome, shape)
    scores = []
    for ep in episodes:
        env = env_factory(ep.seed)
        outcome = rollout(net, env, ep.max_steps)
        scores.append(fitness(outcome) / ep.norm)
    return aggregate_fitness(scores, lam, mode)
