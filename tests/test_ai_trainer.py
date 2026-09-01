"""The training loop end to end.

The load-bearing test here is that fitness actually improves. Everything else
in this package can look correct and still be broken in a way that only shows
up as an agent that never learns — and S7 reads chamber difficulty off that
agent, so a silently non-learning trainer produces confident, wrong numbers.
"""

import json

import numpy as np
import pytest

from gravi.ai import episodes, persistence, trainer
from gravi.ai.env import StubEnvironment
from gravi.ai.ftnn import FTNN
from gravi.ai.metrics import summarise
from gravi.field import Charge


def make_env(seed):
    return StubEnvironment(seed=seed)


# --- the loop learns ---------------------------------------------------------


def test_training_improves_on_a_learnable_task():
    result = trainer.run(
        env_factory=make_env, generations=15, population=24, seed=3
    )
    assert result.history[-1].mean > result.history[0].mean
    assert result.best.fitness > result.history[0].best


def test_a_run_is_reproducible_from_its_seed():
    kwargs = dict(env_factory=make_env, generations=5, population=12, seed=9)
    a = trainer.run(**kwargs)
    b = trainer.run(**kwargs)
    assert np.array_equal(a.best.genome, b.best.genome)
    assert a.best.fitness == b.best.fitness
    assert [s.as_dict() for s in a.history] == [
        # elapsed is wall clock and will differ; everything else must not.
        dict(s.as_dict(), elapsed=t.elapsed) for s, t in zip(b.history, a.history)
    ]


def test_different_seeds_produce_different_runs():
    a = trainer.run(env_factory=make_env, generations=4, population=10, seed=1)
    b = trainer.run(env_factory=make_env, generations=4, population=10, seed=2)
    assert not np.array_equal(a.best.genome, b.best.genome)


def test_history_has_one_entry_per_generation():
    result = trainer.run(env_factory=make_env, generations=6, population=8, seed=1)
    assert [s.gen for s in result.history] == list(range(6))


def test_the_best_genome_is_runnable_as_a_policy():
    result = trainer.run(env_factory=make_env, generations=3, population=8, seed=1)
    net = result.network()
    assert net.decide((0.0, 0.0, 0.5)) in (Charge.ATTRACT, Charge.REPEL, Charge.NEUTRAL)


def test_the_trainer_uses_the_environment_it_was_given():
    """No hidden global level state: if the trainer sourced its own
    environment, this factory would never be called."""
    seen = []

    def factory(seed):
        seen.append(seed)
        return StubEnvironment(seed=seed)

    trainer.run(env_factory=factory, generations=2, population=5, seed=42)
    assert seen, "trainer never called the factory it was handed"
    assert set(seen) == {42}


def test_observation_width_is_taken_from_the_environment():
    result = trainer.run(env_factory=make_env, generations=1, population=4, seed=1)
    assert result.shape.inputs == StubEnvironment.observation_size
    assert result.shape.outputs == FTNN.OUTPUTS


def test_multi_episode_scoring_runs_every_episode():
    seen = []

    def factory(seed):
        seen.append(seed)
        return StubEnvironment(seed=seed)

    trainer.run(env_factory=factory, generations=1, population=4, seed=1,
                episodes_per_genome=3)
    assert len(set(seen)) == 3
    # 4 genomes x 3 episodes, plus one probe environment built up front to read
    # observation_size off it.
    assert len(seen) == 13


def test_the_probe_environment_can_be_skipped():
    """Passing observation_size explicitly avoids constructing an environment
    just to ask how wide it is — worth it when that construction is expensive."""
    seen = []

    def factory(seed):
        seen.append(seed)
        return StubEnvironment(seed=seed)

    trainer.run(env_factory=factory, generations=1, population=4, seed=1,
                observation_size=StubEnvironment.observation_size)
    assert len(seen) == 4  # one per genome, no probe


def test_elitism_never_exceeds_the_population():
    """A population of 1 would otherwise blow up inside breed()."""
    result = trainer.run(env_factory=make_env, generations=2, population=1, seed=1)
    assert len(result.history) == 2


def test_rejects_nonsense_sizes():
    with pytest.raises(ValueError):
        trainer.run(env_factory=make_env, generations=0, population=4)
    with pytest.raises(ValueError):
        trainer.run(env_factory=make_env, generations=1, population=0)


# --- aggregation -------------------------------------------------------------


def test_a_single_episode_aggregates_to_itself():
    assert episodes.aggregate_fitness([4.0], lam=0.5) == pytest.approx(4.0)
    assert episodes.aggregate_fitness([4.0], lam=0.5, mode="min") == pytest.approx(4.0)


def test_the_variance_penalty_punishes_inconsistency():
    steady = episodes.aggregate_fitness([5.0, 5.0], lam=1.0)
    swingy = episodes.aggregate_fitness([0.0, 10.0], lam=1.0)
    assert steady > swingy  # same mean, different consistency


def test_min_mode_takes_the_worst_episode():
    assert episodes.aggregate_fitness([9.0, 1.0, 4.0], lam=0.0, mode="min") == 1.0


def test_unknown_aggregate_mode_is_an_error():
    with pytest.raises(ValueError):
        episodes.aggregate_fitness([1.0], lam=0.0, mode="wishful")


def test_generate_seeds_is_deterministic_and_leads_with_the_base():
    assert episodes.generate_seeds(7, 4) == episodes.generate_seeds(7, 4)
    assert episodes.generate_seeds(7, 4)[0] == 7
    assert len(set(episodes.generate_seeds(7, 5))) == 5


def test_a_truncated_rollout_says_so():
    shape = FTNN.shape(inputs=3, hidden=4)
    net = FTNN(np.zeros(shape.genome_size, dtype=np.float32), shape)
    outcome = episodes.rollout(net, StubEnvironment(seed=1), max_steps=5)
    assert outcome["truncated"] is True
    assert outcome["steps"] == 5


# --- metrics -----------------------------------------------------------------


def test_metrics_record_best_mean_worst_and_wall_clock():
    stats = summarise(2, np.array([1.0, 2.0, 6.0]), elapsed=0.25)
    assert (stats.best, stats.mean, stats.worst) == (6.0, 3.0, 1.0)
    assert stats.elapsed == 0.25
    assert stats.gen == 2


def test_metrics_render_one_line():
    line = summarise(0, np.array([1.0, 2.0]), elapsed=0.1).line()
    assert "gen" in line and "best" in line


# --- persistence -------------------------------------------------------------


def test_a_population_round_trips_exactly(tmp_path):
    shape = FTNN.shape(inputs=3, hidden=4)
    pop = [np.random.default_rng(i).standard_normal(shape.genome_size, dtype=np.float32)
           for i in range(5)]
    path = tmp_path / "pop.json"
    assert persistence.save_population(pop, path, shape=shape, meta={"seed": 1}) is True

    loaded = persistence.load_population(path)
    assert len(loaded) == 5
    assert loaded.shape == shape
    assert loaded.meta["seed"] == 1
    # Bit-for-bit, not merely close — reproducibility claims depend on it.
    assert all(np.array_equal(a, b) for a, b in zip(pop, loaded.genomes))


def test_a_checkpoint_is_plain_json_the_browser_can_read(tmp_path):
    """No numpy on the other side of the wire (spec section 8.6)."""
    shape = FTNN.shape(inputs=3, hidden=4)
    path = tmp_path / "pop.json"
    persistence.save_population([np.zeros(shape.genome_size, dtype=np.float32)],
                                path, shape=shape)
    payload = json.loads(path.read_text())
    assert payload["shape"]["outputs"] == 3
    assert isinstance(payload["genomes"][0], list)


def test_saving_a_population_fails_soft(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise OSError("read-only filesystem")

    monkeypatch.setattr("pathlib.Path.write_text", _raise)
    shape = FTNN.shape(inputs=3, hidden=4)
    ok = persistence.save_population(
        [np.zeros(shape.genome_size, dtype=np.float32)],
        tmp_path / "x.json", shape=shape,
    )
    assert ok is False


def test_loading_a_missing_file_fails_soft(tmp_path):
    assert persistence.load_population(tmp_path / "nope.json") is None


def test_a_corrupt_checkpoint_is_loud_not_silent(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    with pytest.raises(ValueError):
        persistence.load_population(path)


def test_a_genome_of_the_wrong_length_is_caught_on_load(tmp_path):
    shape = FTNN.shape(inputs=3, hidden=4)
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({
        "version": persistence.FORMAT_VERSION,
        "shape": shape.as_dict(),
        "meta": {},
        "genomes": [[0.0, 1.0]],
    }))
    with pytest.raises(ValueError):
        persistence.load_population(path)


def test_a_future_format_version_is_rejected(tmp_path):
    shape = FTNN.shape(inputs=3, hidden=4)
    path = tmp_path / "future.json"
    path.write_text(json.dumps({
        "version": persistence.FORMAT_VERSION + 1,
        "shape": shape.as_dict(),
        "meta": {},
        "genomes": [],
    }))
    with pytest.raises(ValueError):
        persistence.load_population(path)


def test_a_trained_run_can_be_saved_and_resumed(tmp_path):
    result = trainer.run(env_factory=make_env, generations=3, population=6, seed=4)
    path = tmp_path / "run.json"
    assert persistence.save_population(
        result.final_population, path, shape=result.shape, meta=result.meta()
    ) is True

    loaded = persistence.load_population(path)
    assert len(loaded) == 6
    assert loaded.meta["generations"] == 3
    # The resumed population is usable as networks without further ceremony.
    net = FTNN(loaded.genomes[0], loaded.shape)
    assert net.decide((0.0, 0.0, 0.1)) in (Charge.ATTRACT, Charge.REPEL, Charge.NEUTRAL)
