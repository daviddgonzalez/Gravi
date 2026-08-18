"""The generation loop.

Ported from BlueBall's trainer, but only its middle: evaluate the population,
sort by index, track the best, record stats, breed, repeat. BlueBall's
evaluators built a `World`, registered collisions and loaded a level, and none
of that survives contact with Gravi.

**The trainer never sources an environment of its own.** It is handed an
`env_factory` and calls it with an episode seed. BlueBall documented the same
discipline for a sharper reason than tidiness: its trainer streamed terrain
through the exact pipeline the live game used, because a trainer that builds
its own level trains an agent on something the player never plays, and every
measurement taken from that agent is then fiction. Gravi inherits the hazard
with interest — S7 reads difficulty off a trained agent, so if the trainer's
chamber and the player's chamber differ at all, the generator will confidently
emit chambers rated 0.4 that play at 0.9.

DETERMINISM: all GA randomness comes from one `ga_seed` generator, drawn in a
fixed order, so two runs with the same seed produce byte-identical results.
Environment randomness is the environment's business and comes from its seed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np

from .env import score_of
from .episodes import EnvFactory, EpisodeSpec, evaluate_genome, generate_seeds
from .ftnn import FTNN, Shape
from .ga import breed
from .genome import seed_population
from .metrics import GenerationStats, summarise

__all__ = ["TrainingResult", "run", "DEFAULTS"]


#: GA hyperparameters. BlueBall kept these in its global config; here they are
#: local to the trainer, because nothing else in Gravi has an opinion about
#: tournament size and a global would invite one.
DEFAULTS = {
    "elitism": 1,
    "tournament_k": 4,
    "mutation_rate": 0.1,
    "mutation_sigma": 0.1,
    #: Variance penalty in the per-genome score (mean - lam*std). Zero by
    #: default: with one episode per genome the std is 0 and it has no effect,
    #: so a non-zero default would be a silent no-op until it suddenly wasn't.
    "lam": 0.0,
    "aggregate": "mean_std",
}


@dataclass
class TrainingResult:
    """What a run produced."""

    history: list[GenerationStats]
    best_genome: np.ndarray
    best_fitness: float
    shape: Shape
    final_population: list[np.ndarray] = field(default_factory=list)

    @property
    def best(self) -> "BestGenome":
        """The winning genome and its score, together."""
        return BestGenome(genome=self.best_genome, fitness=self.best_fitness)

    def network(self) -> FTNN:
        """The best genome as a runnable policy."""
        return FTNN(self.best_genome, self.shape)

    def meta(self) -> dict:
        """A JSON-safe description of the run, for a checkpoint sidecar."""
        return {
            "generations": len(self.history),
            "best_fitness": self.best_fitness,
            "shape": self.shape.as_dict(),
            "history": [s.as_dict() for s in self.history],
        }


@dataclass(frozen=True)
class BestGenome:
    genome: np.ndarray
    fitness: float


def run(
    *,
    env_factory: EnvFactory,
    generations: int,
    population: int,
    seed: int = 0,
    observation_size: int | None = None,
    hidden: int | None = None,
    episodes: Sequence[EpisodeSpec] | None = None,
    episodes_per_genome: int = 1,
    max_steps: int = 10_000,
    fitness=score_of,
    lam: float | None = None,
    aggregate: str | None = None,
    elitism: int | None = None,
    tournament_k: int | None = None,
    mutation_rate: float | None = None,
    mutation_sigma: float | None = None,
    map_fn: Callable[[Callable, Iterable], Iterable] = map,
    on_generation: Callable[[GenerationStats], None] | None = None,
) -> TrainingResult:
    """Evolve a population against `env_factory` and return the best genome.

    `env_factory(seed)` builds one environment. It is called fresh for every
    episode, so nothing leaks between evaluations.

    `observation_size` defaults to asking the environment, which is the right
    answer whenever the environment knows — pass it only when building a probe
    environment is expensive.

    `episodes` gives explicit control over what each genome is scored on;
    otherwise `episodes_per_genome` seeds are derived from `seed`. Scoring a
    genome on more than one episode is what stops it memorising a single
    chamber, at linear cost in evaluation time.

    `map_fn` is the parallelism strategy. The default `map` is serial and
    in-process. A `multiprocessing.Pool(N).imap` works only if `env_factory`
    and `fitness` are picklable — a module-level function or a class, not a
    lambda or a closure.
    """
    if generations < 1:
        raise ValueError(f"generations must be >= 1, got {generations}")
    if population < 1:
        raise ValueError(f"population must be >= 1, got {population}")
    if episodes_per_genome < 1:
        raise ValueError(
            f"episodes_per_genome must be >= 1, got {episodes_per_genome}"
        )

    lam = DEFAULTS["lam"] if lam is None else lam
    aggregate = DEFAULTS["aggregate"] if aggregate is None else aggregate
    elitism = DEFAULTS["elitism"] if elitism is None else elitism
    tournament_k = DEFAULTS["tournament_k"] if tournament_k is None else tournament_k
    mutation_rate = DEFAULTS["mutation_rate"] if mutation_rate is None else mutation_rate
    mutation_sigma = (
        DEFAULTS["mutation_sigma"] if mutation_sigma is None else mutation_sigma
    )
    # Elitism larger than the population would make breed() raise deep in the
    # loop, after the first generation has already been paid for.
    elitism = min(elitism, population)

    if observation_size is None:
        observation_size = int(env_factory(seed).observation_size)
    shape = FTNN.shape(inputs=observation_size, hidden=hidden)

    if episodes is None:
        episodes = [
            EpisodeSpec(seed=s, max_steps=max_steps)
            for s in generate_seeds(seed, episodes_per_genome)
        ]
    episodes = tuple(episodes)
    if not episodes:
        raise ValueError("run requires a non-empty episodes list")

    ga_rng = np.random.default_rng(seed)
    pop = seed_population(size=population, shape=shape, rng=ga_rng)

    history: list[GenerationStats] = []
    best_genome = pop[0].copy()
    best_fitness = -np.inf

    def score(genome: np.ndarray) -> float:
        return evaluate_genome(
            genome, shape, episodes, env_factory,
            fitness=fitness, lam=lam, mode=aggregate,
        )

    for gen in range(generations):
        started = time.perf_counter()
        fitnesses = np.asarray(list(map_fn(score, pop)), dtype=np.float64)
        stats = summarise(gen, fitnesses, time.perf_counter() - started)

        gen_best_idx = int(np.argmax(fitnesses))
        if float(fitnesses[gen_best_idx]) > best_fitness:
            best_fitness = float(fitnesses[gen_best_idx])
            best_genome = pop[gen_best_idx].copy()

        history.append(stats)
        if on_generation is not None:
            on_generation(stats)

        # The final generation is scored and recorded but not bred — breeding
        # it would return a population nothing ever evaluates.
        if gen < generations - 1:
            pop = breed(
                pop, fitnesses, ga_rng,
                elitism=elitism,
                tournament_k=tournament_k,
                mutation_rate=mutation_rate,
                mutation_sigma=mutation_sigma,
            )

    return TrainingResult(
        history=history,
        best_genome=best_genome,
        best_fitness=best_fitness,
        shape=shape,
        final_population=pop,
    )
