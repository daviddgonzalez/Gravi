# Web build

Gravi targets the browser via [pygbag](https://pypi.org/project/pygbag/), which
packages a pygame-ce app to WebAssembly.

    pygbag --build .        # produce build/web/
    pygbag .                # build + serve on http://localhost:8000

Verified working with pygbag 0.9.3 on 2026-08-11.

## Constraints this imposes

- `main.py` must stay at the repo root — pygbag packages the directory it is
  given and looks for `main.py` there.
- The frame loop must `await asyncio.sleep(0)` every frame or the browser tab
  locks up.
- Runtime dependencies must be pure Python or shipped by the pygbag runtime.
  This is why Gravi has no pymunk and no physics engine (see the slice 1 plan).
- `main.py` must put `src/` on `sys.path` itself. Natively `pip install -e .`
  makes `import gravi` work; the browser has no install step and runs `main.py`
  straight out of the packaged directory, so the src layout is invisible there.
  Without the shim, `import gravi` fails, pygbag falls back to hunting for a
  PyPI package named `gravi`, and gets a 404 from `pypi.org/simple/gravi/`. Do
  not remove the `sys.path.insert` at the top of `main.py`.

  The symptom is a **grey** screen that never changes after click-to-start.
  Grey is pygbag's own "Loading, please wait ..." page, so a grey screen always
  means boot never handed control to `main.py` — the app is not merely drawing
  the wrong colour. Once `main.py` runs, the page turns near-black (COLOR_BG).
  Grey vs black is the fastest way to tell a boot failure from a game bug.
- Writing to disk (tuning presets, edited rooms) works natively but not in the
  browser build; save paths must fail soft rather than raise.

## Notes

- `pygbag --build .` walks the **entire** directory it's given — it does not
  read `.gitignore`. On a fresh checkout with `.venv/` inside the repo root,
  it swept the whole virtualenv into the package and hard-failed with
  `ERROR: MP3 audio format is not allowed on web, convert
  .venv/lib/python3.12/site-packages/pygame/examples/data/metadata.mp3 to
  ogg` — an asset from pygame-ce's own bundled examples, not Gravi code.
- pygbag's own default ignore list only skips a directory literally named
  `venv`, not `.venv`, and its dotfolder skip only matches names that start
  with `.` at the *first* path character — a `.venv` folder one level down
  still gets walked. The fix is the tool's own documented mechanism: a
  `pygbag.ini` in the repo root with an explicit `ignoreDirs` entry:

  ```ini
  [DEPENDENCIES]
  ignoreDirs = ["/.venv"]
  ignoreFiles = []
  ```

  This file is committed alongside this doc. Without it, `pygbag --build .`
  fails on any machine whose venv lives at `.venv/` inside the project.
- `.pytest_cache/`, `src/gravi.egg-info/`, `tests/`, and `docs/` still get
  swept into the package (harmless — plain text, no forbidden formats — just
  bloat). Not excluded for now since they don't break the build; revisit the
  ignore list if that changes.
- Non-fatal warnings seen during the build: `Black not found for processing`
  (pygbag's optional formatter isn't installed) and `ffmpeg: not found`
  (optional audio recompression). Neither affected the build output or exit
  code; both tools are absent from this venv on purpose.
- First build downloaded and cached the pygbag CDN template/runtime
  (`build/web-cache/`); this needs network access once, then is reused.
  Wall-clock time for `pygbag --build .` after the cache was warm: a few
  seconds. `pygbag .` (serve) probe returned `HTTP 200` from
  `http://localhost:8000/` with no traceback in the server log.
- Build output: `build/web/index.html`, `build/web/gravi.apk`,
  `build/web/gravi.tar.gz`, `build/web/favicon.png`.
- Verified in Chrome on 2026-08-12: after click-to-start the canvas renders
  near-black at 1280x720. The build machine has no browser, so this half of
  the check is a human step — the agent-side build check cannot catch a
  browser-only import failure, which is precisely how the src-layout bug above
  survived the first pass.
- Benign console noise, expected on every run, not worth chasing:
  - `** MEDIA USER ACTION REQUIRED **` — pygbag's click-to-start gate, imposed
    by browser autoplay policy.
  - `PyMain: BrowserFS not found` / 404 on `//cdn/<ver>//browserfs.min.js` —
    the loader asks for a file the local CDN cache does not carry. It only
    affects the emulated writable filesystem, which Gravi already treats as
    unavailable in the browser.
  - 404s on `xterm*.js.map` and `/.well-known/appspecific/com.chrome.devtools.json`
    — sourcemap and devtools probes, not app code.
- After a rebuild, reload with a cache bypass (Ctrl+Shift+R). A normal reload
  serves the previously cached `gravi.apk`, so a fix appears not to work.

## Repeatable build

    tools/build_web.sh            # clean build into build/web/, prints the size
    tools/build_web.sh --serve    # ... then serve it on http://localhost:8000

The script removes a stale `build/web` before rebuilding and keeps
`build/web-cache` (the CDN download) so only the first build needs the
network. It empties `PYTHONPATH` for the reason in the note above, and it
finds the `.apk` rather than assuming `gravi.apk` — see the naming trap below.

It also creates `build/web` itself before invoking pygbag. pygbag makes that
directory only on a cold build; with the CDN cache already present it skips
the step and then dies with `FileNotFoundError` opening the apk for writing.

### The archive is named after the directory, not the project

pygbag names the package after the folder it was told to package. Building
from a checkout in `Gravi/` gives `gravi.apk`; building from a worktree in
`s4-ship-layer/` gives `s4-ship-layer.apk`, and `index.html` is generated to
match. Nothing breaks as long as both come from the same build — but anything
that hardcodes `gravi.apk` breaks the moment someone builds from a worktree or
a differently named clone.

## Frame cost

    SDL_VIDEODRIVER=dummy python tools/perf_probe.py --frames 600 --seed 1

Runs the real simulation and a mirror of `main.py`'s draw block with no
display, and reports mean/p95 frame cost. `--seed` scripts the input, so a run
replays exactly; the `checksum` line is simulation state and is identical on
any machine for a given seed, which is what makes that testable.

Measured on 2026-08-17 at commit `79fd949`, 600 frames, seed 1:

| where | mean | p95 | draw | sim |
|---|---|---|---|---|
| dev box (WSL2) | 0.905 ms | 1.889 ms | 0.890 ms | 0.016 ms |
| ubuntu-latest runner | 0.715 ms | 0.923 ms | 0.706 ms | 0.009 ms |

Against a 16.67 ms budget that is about 5%. The split is the point: the
renderer costs fifty times what the simulation does, so a frame-cost
regression is nearly always something new being drawn.

The probe is **not** a CI gate. Runner hardware is shared and noisy, and a
threshold would fail for reasons that have nothing to do with Gravi. It prints
into the job summary so a regression is visible to anyone who looks.

**Drift risk:** `main.py` keeps its draw sequence inline in the frame loop, so
there is no function the probe can call. `tools/perf_probe.py` mirrors that
block by hand. Change the draw order in one and change it in the other, or the
probe starts reporting the cost of a frame the game no longer draws.

## Deploy

`.github/workflows/deploy.yml` publishes `build/web/` to GitHub Pages on every
push to `main`, and can be run by hand (`workflow_dispatch`) to publish a
branch before merging it.

- **Prerequisite, one time:** repo Settings → Pages → Source = **GitHub
  Actions**. Without it the deploy job fails; the build job still passes,
  which is a confusing way to find out.
- Published at <https://daviddgonzalez.github.io/Gravi/>.
- `.nojekyll` is written into the output, or Pages runs it through Jekyll and
  drops anything whose name starts with an underscore.

### Cache busting

The payload is fetched by name from inside `index.html`, and that name is the
same on every build, so a browser holding the previous archive replays the
previous game — the stale-`gravi.apk` trap, with a CDN cache instead of a dev
server.

The deploy rewrites the two `platform.fopen(...)` call sites in `index.html`
to append `?v=<commit sha>`. That argument is only ever a fetch URL:
`aio.filelike.fopen` passes it through `fix_url` and writes the response body
to its own `mktemp` file, so a query suffix cannot confuse the unpacker. The
`bundle` and `archive` names, which *do* become filesystem paths under
`/data/data/`, are deliberately left alone.

A local `pygbag .` serve has no such rewrite. Reload with Ctrl+Shift+R there.
