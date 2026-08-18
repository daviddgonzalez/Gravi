"""The seam the GA trains against.

What the agent actually perceives is session S5's design work, because the
same encoding has to serve the rival. These tests pin the *shape* of the seam
so S5's real encoding is a drop-in, and pin the stub hard enough that a broken
GA fails here rather than silently in a training run.
"""

import pytest

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


def test_observation_width_is_declared_up_front():
    """The network sizes its input layer from this, so it must be knowable
    before the first observation exists."""
    env = StubEnvironment(seed=1)
    width = env.observation_size
    env.reset()
    assert width == len(env.observe())


def test_actions_are_the_three_charges_and_nothing_else():
    env = StubEnvironment(seed=1)
    env.reset()
    for charge in (Charge.ATTRACT, Charge.REPEL, Charge.NEUTRAL):
        env.act(charge)
    with pytest.raises((ValueError, TypeError)):
        env.act(7)


def test_reset_restores_the_starting_state():
    env = StubEnvironment(seed=4)
    env.reset()
    first = env.observe()
    for _ in range(10):
        env.act(Charge.REPEL)
        env.step()
    assert env.observe() != first
    env.reset()
    assert env.observe() == first


def test_same_seed_same_trajectory():
    def trace(seed):
        env = StubEnvironment(seed=seed)
        env.reset()
        out = []
        while not env.done:
            env.act(Charge.ATTRACT)
            env.step()
            out.append(env.observe())
        return out

    assert trace(11) == trace(11)


def test_different_seeds_start_somewhere_different():
    a, b = StubEnvironment(seed=1), StubEnvironment(seed=2)
    a.reset()
    b.reset()
    assert a.observe() != b.observe()


def test_the_task_is_learnable():
    """The stub's only job is to fail loudly if the GA is broken, which it can
    only do if a competent policy outscores a do-nothing one."""

    def run(policy):
        env = StubEnvironment(seed=7)
        env.reset()
        while not env.done:
            env.act(policy(env.observe()))
            env.step()
        return env.outcome()["score"]

    def chase(obs):
        _pos, _vel, error = obs
        return Charge.ATTRACT if error > 0 else Charge.REPEL

    def idle(_obs):
        return Charge.NEUTRAL

    assert run(chase) > run(idle)


def test_stepping_before_reset_is_an_error():
    env = StubEnvironment(seed=1)
    with pytest.raises(RuntimeError):
        env.step()
