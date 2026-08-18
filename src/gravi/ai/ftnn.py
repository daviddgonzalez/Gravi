"""Fixed-Topology Neural Network (FTNN) used by AI agents.

A two-layer fully-connected network: INPUT_SIZE inputs → 12 tanh hidden → 6
outputs. The 6 outputs correspond one-to-one with the `Action` enum values;
the trainer's `FTNNAgent.act()` picks `argmax` to choose an action.

`FTNN_INPUTS` is imported from `ai/observation.py` (its `INPUT_SIZE`) so the
network's input layer can never drift from the adapter that feeds it. With the
current enriched-Observation layout that is 37 inputs:
    [W1 (37*12=444) | b1 (12) | W2 (12*6=72) | b2 (6)]
    GENOME_SIZE = 444 + 12 + 72 + 6 = 534
"""

from __future__ import annotations

import numpy as np

from .observation import INPUT_SIZE

FTNN_INPUTS = INPUT_SIZE
FTNN_HIDDEN = 12
FTNN_OUTPUTS = 6   # one per Action

_W1_SIZE = FTNN_INPUTS * FTNN_HIDDEN
_B1_SIZE = FTNN_HIDDEN
_W2_SIZE = FTNN_HIDDEN * FTNN_OUTPUTS
_B2_SIZE = FTNN_OUTPUTS

GENOME_SIZE = _W1_SIZE + _B1_SIZE + _W2_SIZE + _B2_SIZE


# Legacy genome support: genomes trained before the jump-state inputs existed
# used a 35-input observation (GENOME_SIZE 510). They load into the current
# 37-input net by inserting zero weights for the two new input rows of W1, so
# the new inputs contribute nothing and behavior is identical to the legacy
# net. New training always produces current-size genomes; this only affects
# LOADING old genomes/assets.
_LEGACY_INPUTS = 35
_LEGACY_W1_SIZE = _LEGACY_INPUTS * FTNN_HIDDEN                       # 420
LEGACY_GENOME_SIZE = _LEGACY_W1_SIZE + _B1_SIZE + _W2_SIZE + _B2_SIZE  # 510


def migrate_genome(genome: np.ndarray) -> np.ndarray:
    """Return a current-size genome. Current-size input is returned unchanged;
    a legacy (35-input) genome is expanded by zero-padding the new W1 input
    rows. Any other shape is an error."""
    if genome.shape == (GENOME_SIZE,):
        return genome
    if genome.shape == (LEGACY_GENOME_SIZE,):
        pad = np.zeros((FTNN_INPUTS - _LEGACY_INPUTS) * FTNN_HIDDEN, dtype=np.float32)
        return np.concatenate([
            genome[:_LEGACY_W1_SIZE].astype(np.float32),
            pad,
            genome[_LEGACY_W1_SIZE:].astype(np.float32),
        ])
    raise ValueError(
        f"genome of shape {genome.shape} is neither current ({GENOME_SIZE},) "
        f"nor legacy ({LEGACY_GENOME_SIZE},)"
    )


class FTNN:
    """An INPUT_SIZE → 12 tanh → 6 fully-connected network. Pure numpy."""

    def __init__(self, genome: np.ndarray) -> None:
        genome = migrate_genome(genome)
        if genome.dtype != np.float32:
            genome = genome.astype(np.float32)
        else:
            genome = genome.copy()

        i = 0
        self._W1 = genome[i:i + _W1_SIZE].reshape(FTNN_INPUTS, FTNN_HIDDEN)
        i += _W1_SIZE
        self._b1 = genome[i:i + _B1_SIZE]
        i += _B1_SIZE
        self._W2 = genome[i:i + _W2_SIZE].reshape(FTNN_HIDDEN, FTNN_OUTPUTS)
        i += _W2_SIZE
        self._b2 = genome[i:i + _B2_SIZE]

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Run one observation through the network. Returns shape (FTNN_OUTPUTS,)."""
        h = np.tanh(x @ self._W1 + self._b1)
        return (h @ self._W2 + self._b2).astype(np.float32, copy=False)
