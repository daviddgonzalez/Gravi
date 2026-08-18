# Web build

Gravi targets the browser via [pygbag](https://pypi.org/project/pygbag/), which
packages a pygame-ce app to WebAssembly.

    pygbag --build .        # produce build/web/
    pygbag .                # build + serve on http://localhost:8000

Verified working with pygbag 0.9.3 on 2026-08-11.

## Serve it with pygbag, not with a static server

`python -m http.server --directory build/web` looks like it should work and does
not. The page loads, click-to-start works, and then it hangs forever, because
the runtime fetches its own wheels through a **relative** path:

    GET /cdn/cp312/pygame_ce-2.5.7-cp312-cp312-wasm32_bi_emscripten.whl -> 404

`pygbag`'s dev server proxies `/cdn/` out to the pygame-web CDN and caches it; a
static server has nothing to serve there. The symptom is indistinguishable from
a slow first load, so check the server's access log for a 404 under `/cdn/`
before assuming the WASM build is merely slow. Found the hard way on 2026-08-18.

    pygbag --port 8000 main.py    # builds, then serves with the /cdn proxy

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
