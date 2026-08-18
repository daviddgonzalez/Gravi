"""The GA operators and the network they drive.

Ported from BlueBall. These tests pin the behaviour the port must keep —
seeded reproducibility above all, because every difficulty measurement S7
makes rests on a genome scoring the same way twice — and the behaviour it must
change: Gravi's output layer is three-way, not six.
"""

import numpy as np
import pytest

from gravi.ai import ftnn, ga, genome
from gravi.field import Charge


def rng(seed=0):
    return np.random.default_rng(seed)


# --- network shape -----------------------------------------------------------


def test_network_widths_come_from_the_caller_not_a_hardcoded_observation():
    """BlueBall's FTNN imported its input width from observation.py. Gravi's
    observation does not exist yet — S5 designs it — so the width has to be a
    parameter or this whole package blocks on that session."""
    small = ftnn.FTNN.shape(inputs=3, hidden=8)
    big = ftnn.FTNN.shape(inputs=40, hidden=12)
    assert small.genome_size < big.genome_size


def test_genome_size_matches_the_weights_the_network_consumes():
    shape = ftnn.FTNN.shape(inputs=6, hidden=8)
    expected = 6 * 8 + 8 + 8 * 3 + 3  # W1 + b1 + W2 + b2
    assert shape.genome_size == expected


def test_output_layer_is_three_wide():
    """One verb, three states. Not six actions, and not a key bitfield."""
    assert ftnn.FTNN.OUTPUTS == 3
    assert ftnn.FTNN.shape(inputs=5, hidden=4).outputs == 3


def test_network_decodes_to_one_of_three_charges():
    shape = ftnn.FTNN.shape(inputs=6, hidden=8)
    net = ftnn.FTNN(genome.random_genome(shape, rng(1)), shape)
    assert net.decide((0.1, 0.2, 0.3, 0.4, 0.5, 0.6)) in (
        Charge.ATTRACT,
        Charge.REPEL,
        Charge.NEUTRAL,
    )


def test_decide_is_argmax_over_the_three_outputs():
    shape = ftnn.FTNN.shape(inputs=2, hidden=2)
    net = ftnn.FTNN(genome.random_genome(shape, rng(3)), shape)
    obs = (0.4, -0.2)
    winner = int(np.argmax(net.forward(np.asarray(obs, dtype=np.float32))))
    assert net.decide(obs) is ftnn.CHARGE_BY_OUTPUT[winner]


def test_every_output_index_maps_to_a_distinct_charge():
    assert set(ftnn.CHARGE_BY_OUTPUT) == {Charge.REPEL, Charge.NEUTRAL, Charge.ATTRACT}


def test_a_genome_of_the_wrong_length_is_rejected():
    shape = ftnn.FTNN.shape(inputs=6, hidden=8)
    with pytest.raises(ValueError):
        ftnn.FTNN(np.zeros(shape.genome_size + 1, dtype=np.float32), shape)


def test_the_network_is_deterministic():
    shape = ftnn.FTNN.shape(inputs=4, hidden=5)
    g = genome.random_genome(shape, rng(2))
    a, b = ftnn.FTNN(g, shape), ftnn.FTNN(g, shape)
    obs = (0.1, -0.9, 0.3, 0.0)
    assert np.array_equal(a.forward(np.asarray(obs, dtype=np.float32)),
                          b.forward(np.asarray(obs, dtype=np.float32)))


# --- population and reproducibility ------------------------------------------


def test_same_seed_same_population():
    shape = ftnn.FTNN.shape(inputs=6, hidden=8)
    a = genome.seed_population(size=20, shape=shape, rng=rng(5))
    b = genome.seed_population(size=20, shape=shape, rng=rng(5))
    assert all(np.array_equal(x, y) for x, y in zip(a, b))


def test_different_seeds_differ():
    shape = ftnn.FTNN.shape(inputs=6, hidden=8)
    a = genome.seed_population(size=8, shape=shape, rng=rng(5))
    b = genome.seed_population(size=8, shape=shape, rng=rng(6))
    assert not all(np.array_equal(x, y) for x, y in zip(a, b))


def test_a_seeded_population_has_the_right_shape_and_dtype():
    shape = ftnn.FTNN.shape(inputs=6, hidden=8)
    pop = genome.seed_population(size=7, shape=shape, rng=rng(1))
    assert len(pop) == 7
    assert all(g.shape == (shape.genome_size,) for g in pop)
    assert all(g.dtype == np.float32 for g in pop)


# --- operators ---------------------------------------------------------------


def test_crossover_produces_a_child_of_the_same_length():
    a = np.ones(32, dtype=np.float32)
    b = np.zeros(32, dtype=np.float32)
    child = ga.crossover(a, b, rng(0))
    assert child.shape == a.shape
    assert child.dtype == np.float32


def test_crossover_takes_every_gene_from_one_parent_or_the_other():
    a = np.full(64, 1.0, dtype=np.float32)
    b = np.full(64, -1.0, dtype=np.float32)
    child = ga.crossover(a, b, rng(0))
    assert set(np.unique(child)) <= {1.0, -1.0}


def test_crossover_rejects_mismatched_parents():
    with pytest.raises(ValueError):
        ga.crossover(np.zeros(8, dtype=np.float32), np.zeros(9, dtype=np.float32), rng(0))


def test_mutation_rate_zero_is_the_identity():
    g = np.arange(16, dtype=np.float32)
    assert np.array_equal(ga.mutate(g, rng(0), rate=0.0), g)


def test_mutation_does_not_modify_its_input():
    g = np.arange(16, dtype=np.float32)
    before = g.copy()
    ga.mutate(g, rng(0), rate=1.0, sigma=1.0)
    assert np.array_equal(g, before)


def test_mutation_at_rate_one_moves_every_gene():
    g = np.zeros(64, dtype=np.float32)
    out = ga.mutate(g, rng(0), rate=1.0, sigma=1.0)
    assert not np.any(out == 0.0)


def test_tournament_returns_two_distinct_members():
    fits = np.array([1.0, 5.0, 3.0, 9.0, 2.0])
    i, j = ga.tournament_select(fits, rng(0), k=4)
    assert i != j


def test_breed_keeps_the_elite_unchanged():
    pop = [np.full(8, float(i), dtype=np.float32) for i in range(6)]
    fits = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 9.0])
    nxt = ga.breed(pop, fits, rng(0), elitism=1)
    assert np.array_equal(nxt[0], pop[5])  # the fittest survives verbatim
    assert len(nxt) == len(pop)


def test_breeding_is_reproducible_from_the_generator():
    pop = [np.full(8, float(i), dtype=np.float32) for i in range(6)]
    fits = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 9.0])
    a = ga.breed(pop, fits, rng(7), elitism=1)
    b = ga.breed(pop, fits, rng(7), elitism=1)
    assert all(np.array_equal(x, y) for x, y in zip(a, b))
