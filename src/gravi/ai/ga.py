"""Genetic Algorithm operators over flat genome arrays.

All operators are pure functions of their arguments: they take genome
arrays and a numpy Generator, return new arrays. No module-level state.
"""

from __future__ import annotations

import numpy as np


def mutate(
    genome: np.ndarray,
    rng: np.random.Generator,
    *,
    rate: float = 0.1,
    sigma: float = 0.1,
) -> np.ndarray:
    """Return a mutated copy of `genome`. Each gene is perturbed by
    `rng.normal(0, sigma)` with probability `rate`. Input is never modified.
    """
    out = genome.copy()
    if rate <= 0.0:
        return out
    mask = rng.random(out.shape[0]) < rate
    noise = rng.normal(0.0, sigma, size=out.shape[0]).astype(np.float32)
    out[mask] += noise[mask]
    return out


def crossover(
    parent_a: np.ndarray,
    parent_b: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Per-gene uniform crossover. Each gene independently from A or B with 50/50."""
    if parent_a.shape != parent_b.shape:
        raise ValueError(
            f"crossover parents must match shape; got {parent_a.shape} vs {parent_b.shape}"
        )
    mask = rng.random(parent_a.shape[0]) < 0.5
    return np.where(mask, parent_a, parent_b).astype(np.float32, copy=False)


def tournament_select(
    fitnesses: np.ndarray,
    rng: np.random.Generator,
    *,
    k: int = 4,
) -> tuple[int, int]:
    """Sample `k` indices uniformly without replacement; return the indices
    of the two highest-fitness members of that sample. `k` is clamped to
    `len(fitnesses)`.
    """
    n = len(fitnesses)
    k = min(k, n)
    if k < 2:
        raise ValueError("tournament_select requires k >= 2")
    pool = rng.choice(n, size=k, replace=False)
    # Sort the pool indices by their fitness, descending; take top 2.
    pool_sorted = pool[np.argsort(-fitnesses[pool], kind="stable")]
    return int(pool_sorted[0]), int(pool_sorted[1])


def breed(
    population: list[np.ndarray],
    fitnesses: np.ndarray,
    rng: np.random.Generator,
    *,
    elitism: int = 1,
    tournament_k: int = 4,
    mutation_rate: float = 0.1,
    mutation_sigma: float = 0.1,
) -> list[np.ndarray]:
    """Produce the next generation. The top `elitism` genomes pass through
    unchanged; the rest are children of `crossover(parents) → mutate(child)`
    with tournament-selected parents.

    Degenerate case (n=2, elitism=0): tournament_select clamps k to 2, draws
    both indices without replacement, and so every child is bred from the
    same (g0, g1) pair (mutation still introduces noise, but no other
    crossover parents exist). Functionally correct but selection pressure
    collapses to a flat coin flip — callers running tiny populations should
    either bump pop_size, set elitism == 1, or accept the limitation.
    """
    n = len(population)
    if len(fitnesses) != n:
        raise ValueError("fitnesses must match population size")
    if elitism < 0 or elitism > n:
        raise ValueError("invalid elitism count")
    if n < 2 and elitism < n:
        raise ValueError(
            "breed needs population of at least 2 to call tournament_select "
            "(or set elitism == population size to skip breeding)"
        )

    # Elitism: copy the top `elitism` genomes unchanged.
    elite_order = np.argsort(-fitnesses, kind="stable")[:elitism]
    next_gen: list[np.ndarray] = [population[int(i)].copy() for i in elite_order]

    while len(next_gen) < n:
        i, j = tournament_select(fitnesses, rng, k=tournament_k)
        child = crossover(population[i], population[j], rng)
        child = mutate(child, rng, rate=mutation_rate, sigma=mutation_sigma)
        next_gen.append(child)

    return next_gen
