"""Fixed-Topology Neural Network (FTNN), the policy a genome parameterises.

A two-layer fully-connected network: N inputs → H tanh hidden → 3 outputs. The
three outputs are Gravi's whole action space — repel, neutral, attract — and
`decide()` takes the argmax.

Two things changed in the port from BlueBall, both deliberate:

**The input width is a parameter, not an import.** BlueBall's version read
`INPUT_SIZE` from `ai/observation.py` so the network could never drift from the
adapter feeding it. That coupling is right, but Gravi's observation does not
exist yet — session S5 designs it, because the same encoding has to serve the
rival. So the shape travels as an explicit `Shape` alongside the genome, and
the environment is what declares the width (`Environment.observation_size`).
The drift protection survives: a genome carries the shape it was trained at,
and loading it into a different one raises rather than silently reinterpreting
the weights.

**No legacy genome migration.** BlueBall zero-padded weights to load genomes
trained before its jump-state inputs existed. Gravi has no trained genomes yet
and no history to be compatible with; carrying that forward would be importing
someone else's archaeology.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..field import Charge

__all__ = ["Shape", "FTNN", "CHARGE_BY_OUTPUT"]

#: Output index → the charge it selects. Index order is the enum's own order,
#: so an argmax of 0 is the most negative charge and 2 the most positive.
CHARGE_BY_OUTPUT: tuple[Charge, ...] = (Charge.REPEL, Charge.NEUTRAL, Charge.ATTRACT)


@dataclass(frozen=True)
class Shape:
    """The network's dimensions, and the genome length they imply.

    Frozen and carried with the genome: a population, a checkpoint and a
    network all agree on one of these or the load fails loudly.
    """

    inputs: int
    hidden: int
    outputs: int

    @property
    def w1_size(self) -> int:
        return self.inputs * self.hidden

    @property
    def w2_size(self) -> int:
        return self.hidden * self.outputs

    @property
    def genome_size(self) -> int:
        """[ W1 | b1 | W2 | b2 ] laid out flat."""
        return self.w1_size + self.hidden + self.w2_size + self.outputs

    def as_dict(self) -> dict:
        return {"inputs": self.inputs, "hidden": self.hidden, "outputs": self.outputs}

    @classmethod
    def from_dict(cls, data: dict) -> "Shape":
        return cls(
            inputs=int(data["inputs"]),
            hidden=int(data["hidden"]),
            outputs=int(data["outputs"]),
        )


class FTNN:
    """An inputs → hidden (tanh) → 3 fully-connected network. Pure numpy."""

    #: One verb, three states. There is no fourth output.
    OUTPUTS = 3

    #: Hidden width carried over from BlueBall, which trained fine at 12.
    DEFAULT_HIDDEN = 12

    @classmethod
    def shape(cls, *, inputs: int, hidden: int | None = None) -> Shape:
        """The Shape for an observation of `inputs` floats."""
        if inputs < 1:
            raise ValueError(f"inputs must be positive, got {inputs}")
        hidden = cls.DEFAULT_HIDDEN if hidden is None else hidden
        if hidden < 1:
            raise ValueError(f"hidden must be positive, got {hidden}")
        return Shape(inputs=inputs, hidden=hidden, outputs=cls.OUTPUTS)

    def __init__(self, genome: np.ndarray, shape: Shape) -> None:
        if genome.shape != (shape.genome_size,):
            raise ValueError(
                f"genome of shape {genome.shape} does not fit a network of "
                f"{shape.inputs}x{shape.hidden}x{shape.outputs} "
                f"(expected ({shape.genome_size},))"
            )
        self.shape_ = shape
        weights = genome.astype(np.float32, copy=True)

        i = 0
        self._W1 = weights[i:i + shape.w1_size].reshape(shape.inputs, shape.hidden)
        i += shape.w1_size
        self._b1 = weights[i:i + shape.hidden]
        i += shape.hidden
        self._W2 = weights[i:i + shape.w2_size].reshape(shape.hidden, shape.outputs)
        i += shape.w2_size
        self._b2 = weights[i:i + shape.outputs]

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Run one observation through the network. Returns shape (3,)."""
        h = np.tanh(x @ self._W1 + self._b1)
        return (h @ self._W2 + self._b2).astype(np.float32, copy=False)

    def decide(self, observation: Sequence[float]) -> Charge:
        """The charge this policy picks for `observation`. Argmax over the
        three outputs; ties go to the lower index, which numpy already does."""
        obs = np.asarray(observation, dtype=np.float32)
        if obs.shape != (self.shape_.inputs,):
            raise ValueError(
                f"observation of width {obs.shape} does not fit a network "
                f"expecting {self.shape_.inputs} inputs"
            )
        return CHARGE_BY_OUTPUT[int(np.argmax(self.forward(obs)))]
