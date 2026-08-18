"""Genome construction helpers for the FTNN."""

from __future__ import annotations

import numpy as np

from .ftnn import GENOME_SIZE


def random_genome(rng: np.random.Generator) -> np.ndarray:
    """Sample a fresh genome from N(0, 1). Returns float32 ndarray (GENOME_SIZE,)."""
    return rng.standard_normal(GENOME_SIZE, dtype=np.float32)
