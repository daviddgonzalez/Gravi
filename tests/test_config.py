from gravi import config


def test_every_tunable_default_is_inside_its_own_bounds():
    for name, (default, step, lo, hi) in config.TUNABLES.items():
        assert lo <= default <= hi, f"{name} default {default} outside [{lo}, {hi}]"
        assert step > 0, f"{name} step must be positive"


def test_default_tunables_returns_a_fresh_dict():
    a = config.default_tunables()
    b = config.default_tunables()
    a["k_attract"] = 999.0
    assert b["k_attract"] == config.TUNABLES["k_attract"][0]
