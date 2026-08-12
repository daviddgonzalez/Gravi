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
- Not verified here (no browser/display available in this environment): that
  the canvas actually renders or that the browser devtools console is clean.
  A human needs to open `http://localhost:8000` and check both.
