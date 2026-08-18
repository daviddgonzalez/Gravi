#!/usr/bin/env bash
# Build the browser target from clean, and say how big it came out.
#
# Usage:  tools/build_web.sh [--serve]
#
# Everything this script knows the hard way is written up in
# docs/web-build.md — read that before changing anything here.
#
#   - PYTHONPATH is emptied on purpose. A ROS install on the author's machine
#     puts its own site-packages first and pygbag dies before it starts; the
#     same hazard exists on any box with system Python packages.
#   - build/ is removed first because a stale gravi.apk is served in
#     preference to a fresh one, which reliably wastes an hour.
#   - build/web-cache/ is the pygbag CDN download. It is preserved across
#     builds: it needs the network once, and re-fetching it is the slowest
#     part of a cold build.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYGBAG="${PYGBAG:-}"
if [ -z "$PYGBAG" ]; then
    if [ -x .venv/bin/pygbag ]; then
        PYGBAG=".venv/bin/pygbag"
    elif command -v pygbag >/dev/null 2>&1; then
        PYGBAG="pygbag"
    else
        echo "error: pygbag not found. pip install -e '.[dev]'" >&2
        exit 1
    fi
fi

if [ ! -f main.py ]; then
    echo "error: main.py must be at the repo root — pygbag packages the" \
         "directory it is given and looks for main.py there" >&2
    exit 1
fi

# Keep the CDN cache, drop everything else.
if [ -d build/web-cache ]; then
    CACHE_KEEP="$(mktemp -d)"
    mv build/web-cache "$CACHE_KEEP/web-cache"
fi
rm -rf build/web
if [ -n "${CACHE_KEEP:-}" ]; then
    mkdir -p build
    mv "$CACHE_KEEP/web-cache" build/web-cache
    rmdir "$CACHE_KEEP"
fi
# pygbag creates build/web itself only on a cold build; with the CDN cache
# already in place it skips that step and then fails opening the apk for
# writing. Cheap to always create, and it makes the clean build reproducible.
mkdir -p build/web

echo "building with $PYGBAG ..."
PYTHONPATH= "$PYGBAG" --build .

if [ ! -f build/web/index.html ]; then
    echo "error: build reported success but build/web/index.html is missing" >&2
    exit 1
fi

# pygbag names the archive after the directory it packaged, not after the
# project — building from a directory called foo/ yields foo.apk. Find it
# rather than assuming gravi.apk.
APK="$(find build/web -maxdepth 1 -name '*.apk' -print -quit)"
if [ -z "$APK" ]; then
    echo "error: no .apk in build/web — the package was not written" >&2
    exit 1
fi

echo
echo "build/web contents:"
ls -la build/web
echo
echo "total size: $(du -sh build/web | cut -f1)  (apk: $(du -h "$APK" | cut -f1))"

if [ "${1:-}" = "--serve" ]; then
    echo
    echo "serving on http://localhost:8000 — reload with Ctrl+Shift+R, a"
    echo "normal reload serves the cached apk. Grey screen means boot never"
    echo "reached main.py; near-black means the game is running."
    PYTHONPATH= "$PYGBAG" .
fi
