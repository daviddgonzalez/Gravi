"""Genome construction for the FTNN.

A genome is a flat float32 vector of weights, and nothing else — the shape that
interprets it travels alongside (see `ftnn.Shape`) rather than being baked into
a module constant, because Gravi's observation width is not known until session
S5 designs what the agent sees.
"""

from __future__ import annotations

import numpy as np

from .ftnn import Shape

__all__ = ["random_genome", "seed_population"]


def random_genome(shape: Shape, rng: np.random.Generator) -> np.ndarray:
    """Sample a fresh genome from N(0, 1). Returns float32 (genome_size,)."""
    return rng.standard_normal(shape.genome_size, dtype=np.float32)


def seed_population(*, size: int, shape: Shape, rng: np.random.Generator) -> list[np.ndarray]:
    """Generation zero: `size` independent genomes drawn from one generator.

    Drawn in sequence from a single generator rather than from per-genome
    seeds, so one seed reproduces the whole population exactly — which is the
    property every downstream reproducibility claim rests on.
    """
    if size < 1:
        raise ValueError(f"population size must be positive, got {size}")
    return [random_genome(shape, rng) for _ in range(size)]
