"""Headless training entry point: `python -m gravi.ai`.

Exists so session S7 can invoke training as a build step without importing any
of this package's internals. Prints one line per generation, because a long run
that prints nothing is indistinguishable from a hung one.

Runs natively only. Never imports pygame — the box that runs this may have no
display at all (spec section 8.6).
"""

from __future__ import annotations

import argparse
import sys

from . import persistence, trainer
from .env import StubEnvironment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m gravi.ai",
        description="Train a population of agents headlessly and checkpoint it.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--generations", type=int, default=20,
                        help="how many generations to evolve")
    parser.add_argument("--population", type=int, default=32,
                        help="genomes per generation")
    parser.add_argument("--seed", type=int, default=0,
                        help="seeds all GA randomness; the same seed reproduces "
                             "a run exactly")
    parser.add_argument("--out", type=str, default=None,
                        help="write the final population here as JSON; omit to "
                             "train without producing an artifact")
    parser.add_argument("--hidden", type=int, default=None,
                        help="hidden layer width (default: the network's own)")
    parser.add_argument("--episodes", type=int, default=1, metavar="N",
                        help="episodes each genome is scored on; more than one "
                             "costs linear time and buys an agent that "
                             "generalises instead of memorising a seed")
    parser.add_argument("--max-steps", type=int, default=10_000,
                        help="hard cap on the length of one episode")
    parser.add_argument("--aggregate", choices=("mean_std", "min"),
                        default="mean_std",
                        help="how per-episode scores combine into one")
    parser.add_argument("--lam", type=float, default=0.0, metavar="PENALTY",
                        help="variance penalty in mean - lam*std; ignored when "
                             "--aggregate is min or --episodes is 1")
    parser.add_argument("--elitism", type=int, default=None,
                        help="genomes carried to the next generation unchanged")
    parser.add_argument("--mutation-rate", type=float, default=None,
                        help="probability a given gene is perturbed")
    parser.add_argument("--mutation-sigma", type=float, default=None,
                        help="standard deviation of that perturbation")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress the per-generation progress lines")
    return parser


def _make_env(seed: int) -> StubEnvironment:
    """The only environment there is, for now.

    Session S5 designs what the agent actually perceives, and S7 wires the real
    chamber environment in behind this. Until then a run here proves the
    machinery works, not that an agent can play Gravi.
    """
    return StubEnvironment(seed=seed)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.generations < 1:
        print("--generations must be at least 1", file=sys.stderr)
        return 2
    if args.population < 1:
        print("--population must be at least 1", file=sys.stderr)
        return 2
    if args.episodes < 1:
        print("--episodes must be at least 1", file=sys.stderr)
        return 2

    def report(stats):
        print(stats.line(), flush=True)

    result = trainer.run(
        env_factory=_make_env,
        generations=args.generations,
        population=args.population,
        seed=args.seed,
        hidden=args.hidden,
        episodes_per_genome=args.episodes,
        max_steps=args.max_steps,
        aggregate=args.aggregate,
        lam=args.lam,
        elitism=args.elitism,
        mutation_rate=args.mutation_rate,
        mutation_sigma=args.mutation_sigma,
        on_generation=None if args.quiet else report,
    )

    print(f"best fitness {result.best_fitness:.6f} after "
          f"{args.generations} generations")

    if args.out is not None:
        saved = persistence.save_population(
            result.final_population, args.out,
            shape=result.shape, meta=result.meta(),
        )
        if not saved:
            # save_population fails soft because the browser has no writable
            # filesystem. A build step that was asked for an artifact and got
            # none is a different situation, and must not exit 0.
            print(f"could not write {args.out}", file=sys.stderr)
            return 1
        print(f"wrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
