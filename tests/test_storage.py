"""Spec section 8.6: anything that saves must fail soft. The browser has no
writable filesystem, so a save keypress there must be a no-op, never a
traceback. Every test injects a backend so the suite touches neither a real
disk nor a real browser."""

import json

from gravi import storage


def test_round_trips_through_the_backend():
    backend = storage.MemoryBackend()
    storage.save("best", {"chambers": 12}, backend=backend)
    assert storage.load("best", backend=backend) == {"chambers": 12}


def test_missing_key_returns_the_default():
    assert storage.load("nope", default=[], backend=storage.MemoryBackend()) == []


def test_corrupt_value_returns_the_default_instead_of_raising():
    backend = storage.MemoryBackend({"gravi.best": "{not json"})
    assert storage.load("best", default=None, backend=backend) is None


def test_save_fails_soft_when_the_backend_raises():
    class Exploding(storage.MemoryBackend):
        def write(self, key, value):
            raise OSError("read-only filesystem")

    assert storage.save("best", {"a": 1}, backend=Exploding()) is False


def test_load_fails_soft_when_the_backend_raises():
    class Exploding(storage.MemoryBackend):
        def read(self, key):
            raise OSError("device disappeared")

    assert storage.load("best", default="fallback", backend=Exploding()) == "fallback"


def test_keys_are_namespaced():
    backend = storage.MemoryBackend()
    storage.save("best", 1, backend=backend)
    assert list(backend.data) == ["gravi.best"]


def test_save_returns_true_on_success():
    assert storage.save("best", {"a": 1}, backend=storage.MemoryBackend()) is True


def test_unencodable_value_fails_soft_and_leaves_no_partial_write():
    backend = storage.MemoryBackend()
    assert storage.save("best", {1, 2, 3}, backend=backend) is False
    assert backend.data == {}


def test_round_trips_every_json_type():
    backend = storage.MemoryBackend()
    payload = {"a": [1, 2.5, "s", None, True], "b": {"nested": {}}}
    storage.save("blob", payload, backend=backend)
    assert storage.load("blob", backend=backend) == payload


def test_file_backend_round_trips_on_a_real_path(tmp_path):
    backend = storage.FileBackend(tmp_path / "store")
    storage.save("best", {"chambers": 7}, backend=backend)
    assert storage.load("best", backend=backend) == {"chambers": 7}


def test_file_backend_writes_one_file_per_key(tmp_path):
    backend = storage.FileBackend(tmp_path / "store")
    storage.save("best", 1, backend=backend)
    storage.save("other", 2, backend=backend)
    assert sorted(p.name for p in (tmp_path / "store").iterdir()) == [
        "gravi.best.json",
        "gravi.other.json",
    ]


def test_file_backend_reads_back_what_it_wrote_as_plain_json(tmp_path):
    backend = storage.FileBackend(tmp_path / "store")
    storage.save("best", {"chambers": 3}, backend=backend)
    written = (tmp_path / "store" / "gravi.best.json").read_text()
    assert json.loads(written) == {"chambers": 3}


def test_file_backend_missing_directory_loads_the_default(tmp_path):
    backend = storage.FileBackend(tmp_path / "never-created")
    assert storage.load("best", default={}, backend=backend) == {}


def test_file_backend_save_fails_soft_when_the_directory_is_unwritable(tmp_path):
    blocker = tmp_path / "store"
    blocker.write_text("I am a file, not a directory")
    assert storage.save("best", 1, backend=storage.FileBackend(blocker)) is False


def test_default_backend_is_a_file_backend_off_emscripten():
    assert isinstance(storage.default_backend(), storage.FileBackend)


def test_save_and_load_use_the_default_backend_when_none_is_given(monkeypatch, tmp_path):
    backend = storage.FileBackend(tmp_path / "store")
    monkeypatch.setattr(storage, "_DEFAULT_BACKEND", backend)
    assert storage.save("best", {"chambers": 1}) is True
    assert storage.load("best") == {"chambers": 1}


def test_a_key_with_path_separators_cannot_escape_the_store(tmp_path):
    backend = storage.FileBackend(tmp_path / "store")
    assert storage.save("../../escaped", 1, backend=backend) is False
    assert not (tmp_path / "escaped.json").exists()
