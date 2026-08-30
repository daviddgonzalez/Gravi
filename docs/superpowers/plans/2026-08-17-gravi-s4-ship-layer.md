# Session S4 — The ship layer: browser, persistence, CI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task.

**You are session S4 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**Goal:** Close the one gap slice 1's verdict recorded as "worth closing first", and build the machinery that keeps the browser build honest from here on: a fail-soft storage module, a repeatable build, CI, a deploy target, and a headless performance probe.

**Architecture:** Everything here is additive or peripheral. You own `tools/`, `.github/`, `docs/web-build.md` and one new pure module, `src/gravi/storage.py`. **You do not touch `main.py`, `sim.py`, `config.py` or anything under `render/`** — session S1 is rewriting those right now, and wiring storage into the game is a later, one-line job for whoever owns `main.py` when you are done.

**Tech stack:** pygbag 0.9.3, GitHub Actions, pytest. `docs/web-build.md` is unusually good — read it before task 1 and keep it updated as you go.

---

## Task 1: play slice 1 in the browser and write down what happened

**Goal:** Answer the open question slice 1 left: does the feel survive WebAssembly frame pacing?

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Do this first, before S1 merges.** It measures the *slice 1* build, which is a known-good, already-judged artefact. Once the chamber work lands, a bad result no longer tells you whether WASM or the new code caused it.

**Files:**
- Create: `docs/superpowers/runbooks/YYYY-MM-DD-slice-1-browser-feel-check.md`
- Modify: `docs/web-build.md` if anything in the recipe has rotted

**Acceptance criteria:**
- [ ] `.venv/bin/pygbag --build .` completes and `build/web/index.html` exists
- [ ] The build is **played in a real browser for at least five minutes**, chaining orbits — not booted and looked at
- [ ] Measured: frames per second reported by the in-game overlay (added in `b7406cb`), and physics-step saturation, both recorded as numbers
- [ ] An explicit verdict on whether chaining three orbits feels the same as native, better, or worse — and if worse, in what specific way (input latency, frame pacing jitter, or physics stepping)
- [ ] The runbook names the commit SHA it tested

**Verify:** the runbook exists and contains an fps number and a yes/no on parity with native

**Steps:**

- [ ] **Step 1: Build**

```bash
PYTHONPATH= .venv/bin/pygbag --build .
ls -la build/web/
```

- [ ] **Step 2: Serve and play**

```bash
PYTHONPATH= .venv/bin/pygbag .    # serves on http://localhost:8000
```

Reload with a cache bypass (Ctrl+Shift+R) — a normal reload serves the cached `gravi.apk` and you will be testing an old build. A **grey** screen means boot never reached `main.py`; near-black means the game is running. That distinction is in `docs/web-build.md` and it will save you an hour.

- [ ] **Step 3: Write the runbook** in the style of `docs/superpowers/runbooks/2026-08-11-slice-1-feel-verdict.md`: decision, measurements, coverage gaps stated plainly.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/runbooks/ docs/web-build.md
git commit -m "docs: slice 1 browser feel check"
```

---

## Task 2: `storage.py` — persistence that cannot crash the browser

**Goal:** One module that saves and loads small JSON blobs, backed by the filesystem natively and by `localStorage` in the browser, and that never raises.

**Files:**
- Create: `src/gravi/storage.py`
- Test: `tests/test_storage.py`

**Why now:** core spec §8.6 says anything that saves — tuning presets, edited rooms, the player model (§5.2), personal-best paths (§6) — must fail soft and will eventually need browser-side persistence. The rival's whole meta-loop ("it adapted to how I played last night", §5.4) is persistence. Building it as a leaf module now means S8, S9 and S10 all inherit it instead of each inventing one.

**Acceptance criteria:**
- [ ] `storage.save(key, obj) -> bool` and `storage.load(key, default=None) -> Any`; `save` returns `False` rather than raising on any failure
- [ ] Backend is chosen at import time: `localStorage` when `sys.platform == "emscripten"`, otherwise a JSON file under a per-user directory
- [ ] The backend is injectable so tests never touch a real disk or a real browser
- [ ] Round-trips anything `json` can encode; a corrupt stored value loads as the default instead of raising
- [ ] Keys are namespaced (`gravi.<key>`) so the browser origin is not polluted
- [ ] `storage.py` imports no pygame

**Verify:** `PYTHONPATH= .venv/bin/pytest tests/test_storage.py tests/test_purity.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py
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


def test_keys_are_namespaced():
    backend = storage.MemoryBackend()
    storage.save("best", 1, backend=backend)
    assert list(backend.data) == ["gravi.best"]
```

- [ ] **Step 2: Run and watch fail** → `ModuleNotFoundError: No module named 'gravi.storage'`

- [ ] **Step 3: Write the module** — a `Backend` protocol with `read(key)`/`write(key, value)`, a `MemoryBackend`, a `FileBackend`, a `LocalStorageBackend` (guarded by `sys.platform == "emscripten"`, reaching `platform.window.localStorage` the way pygbag exposes it), and a module-level `default_backend()` chosen once.

Wrap **every** call site in `try/except Exception` and return the failure value. This module's contract is that it cannot be the reason a run dies, and a save keypress in a browser must be a no-op, not a traceback.

- [ ] **Step 4: Run** → all PASS

- [ ] **Step 5: Commit**

```bash
git add src/gravi/storage.py tests/test_storage.py tests/test_purity.py
git commit -m "feat(storage): fail-soft key-value persistence for native and browser"
```

---

## Task 3: a repeatable build and a headless perf probe

**Goal:** One command builds the web target from clean; one command reports what a frame costs, without a display.

**Files:**
- Create: `tools/build_web.sh`, `tools/perf_probe.py`
- Test: `tests/test_perf_probe.py` (that the probe runs and reports, not that any specific number holds)

**Acceptance criteria:**
- [ ] `tools/build_web.sh` builds into `build/web/`, exits non-zero on failure, and prints the output size
- [ ] `tools/perf_probe.py` runs N frames with `SDL_VIDEODRIVER=dummy` and prints mean and p95 frame cost in milliseconds
- [ ] The probe takes a `--frames` and a `--seed` flag and is deterministic
- [ ] Neither script imports anything not already in `pyproject.toml`

**Verify:** `PYTHONPATH= SDL_VIDEODRIVER=dummy .venv/bin/python tools/perf_probe.py --frames 600 --seed 1` → prints mean/p95, exits 0

**Note for the probe:** the frame currently costs about 1.10 ms (measured while rejecting the rotate-the-finished-frame camera option — see slice 2 spec §5.3). That is the number to compare against. The probe must measure the **draw path**, not just the simulation, since the sim is cheap and the renderer is where the budget goes.

**Steps:**

- [ ] **Step 1: Write the probe test** — subprocess-invoke it and assert it exits 0 and prints a float.
- [ ] **Step 2: Run and watch fail.**
- [ ] **Step 3: Write both scripts.**
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit**

```bash
git add tools/ tests/test_perf_probe.py
git commit -m "build: repeatable web build and a headless frame-cost probe"
```

---

## Task 4: CI

**Goal:** Every push runs the suite and proves the web build still packages.

**Files:**
- Create: `.github/workflows/ci.yml`

**Acceptance criteria:**
- [ ] Job 1: `pytest` on Python 3.12, with `PYTHONPATH` explicitly emptied (a ROS install on the author's machine poisons it — the same hazard exists on any runner with system Python packages)
- [ ] Job 2: `pygbag --build .` succeeds and uploads `build/web/` as an artifact
- [ ] The workflow runs on push to `main` and on pull requests
- [ ] Total wall clock under five minutes, with the pygbag CDN cache cached between runs

**Verify:** push a branch; both jobs green

**Steps:**

- [ ] **Step 1: Write the workflow.**
- [ ] **Step 2: Push a throwaway branch and watch it run.** Fix until green; do not merge a red workflow "to fix later".
- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run the suite and package the web build on every push"
```

---

## Task 5: deploy the browser build

**Goal:** The game is playable from a URL.

**Files:**
- Create: `.github/workflows/deploy.yml`
- Modify: `README.md` (link), `docs/web-build.md` (deploy section)

**Acceptance criteria:**
- [ ] Pushing to `main` publishes `build/web/` to GitHub Pages
- [ ] The published page loads and plays in a browser — verified by opening it, not by the workflow going green
- [ ] `README.md` links to it
- [ ] Cache headers or a cache-busting query prevent the stale-`gravi.apk` problem that already bites locally

**Default choice:** GitHub Pages, because the build output is static and the repo is already on GitHub. If the user has said otherwise, follow that instead — this is a preference, not a constraint.

**Verify:** open the published URL; the canvas turns near-black and the game responds to input

**Steps:**

- [ ] **Step 1: Write the workflow.**
- [ ] **Step 2: Enable Pages on the repo and push.**
- [ ] **Step 3: Open the URL and play it.** A green workflow is not evidence the page works — the grey-vs-black distinction in `docs/web-build.md` exists because a build can succeed and still never reach `main.py`.
- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy.yml README.md docs/web-build.md
git commit -m "build: publish the browser build to Pages on push to main"
```

---

## When you are done

Report: the browser feel verdict from task 1 (this is the one the other sessions care about), the deployed URL, the measured frame cost from the perf probe, and anything in the pygbag pipeline that looks fragile enough to bite later.
