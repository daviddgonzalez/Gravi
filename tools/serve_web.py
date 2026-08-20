"""Serve the pygbag build so that a rebuild is actually what you get.

pygbag's own dev server is right for a first load and wrong for iterating. The
generated loader fetches the app bundle from a FIXED url with no version in it:

    platform.fopen("s1-chambers-and-rotation.apk", "rb")

Once the browser has that url cached, reloading the page cannot produce a new
build. The page reloads, the runtime boots, and it unpacks yesterday's game —
with no error anywhere, because nothing failed. Ctrl+Shift+R does not help, and
neither does closing the tab: the request is simply never made again. Measured
on 2026-08-20: two page loads in a row served from cache, the last fetch of
the bundle four reloads earlier.

So this server splits the two things pygbag's server treats alike:

- **The app bundle** (`index.html`, `.apk`, `.tar.gz`) is served `no-store`.
  It changes every build, it is small, and a stale one is invisible.
- **The runtime** (`/cdn/...`) is proxied from pygame-web.github.io and cached
  on disk, then served as immutable. It is ~10 MB, it is versioned in its own
  url, and it changes when pygbag does — roughly never. Without the disk cache
  every reload would re-download the interpreter, which is the reason pygbag's
  server proxies it in the first place.

Usage:

    PYTHONPATH=src .venv/bin/pygbag --build main.py    # build only
    python tools/serve_web.py [port]                   # serve it

Stdlib only, like everything else here.
"""

from __future__ import annotations

import http.server
import pathlib
import shutil
import socketserver
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "build" / "web"
CDN_CACHE = ROOT / "build" / "cdn-cache"
UPSTREAM = "https://pygame-web.github.io/cdn/"

# Everything the loader pulls is one of these; anything else is a typo we would
# rather see as a 404 than silently fetch from the internet.
CONTENT_TYPES = {
    ".js": "application/javascript",
    ".json": "application/json",
    ".wasm": "application/wasm",
    ".data": "application/octet-stream",
    ".whl": "application/octet-stream",
    ".css": "text/css",
    ".html": "text/html",
    ".py": "text/x-python",
    ".ogg": "audio/ogg",
    ".png": "image/png",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib's spelling
        path = self._clean_path()
        if path.startswith("/cdn/"):
            self._serve_cdn(path[len("/cdn/"):])
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        path = self._clean_path()
        if path.startswith("/cdn/"):
            self._serve_cdn(path[len("/cdn/"):], body=False)
            return
        super().do_HEAD()

    def _clean_path(self) -> str:
        """The loader emits `//cdn/...` for some assets and `/cdn/...` for
        others. Collapse repeats rather than matching both spellings."""
        path = self.path.split("?", 1)[0]
        while "//" in path:
            path = path.replace("//", "/")
        return path

    def end_headers(self) -> None:
        """Applies to the app bundle only — `_serve_cdn` writes its own."""
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def send_head(self):
        """Never answer 304 for the bundle. A conditional request that the
        browser makes anyway must still get the new bytes, or `no-store` buys
        us nothing."""
        for header in ("If-Modified-Since", "If-None-Match"):
            while header in self.headers:
                del self.headers[header]
        return super().send_head()

    def _serve_cdn(self, rest: str, body: bool = True) -> None:
        if ".." in rest or rest.startswith("/"):
            self.send_error(404, "no")
            return

        cached = CDN_CACHE / rest
        if not cached.exists():
            if not self._fetch(rest, cached):
                return

        data = cached.read_bytes()
        suffix = cached.suffix.lower()
        self.send_response(200)
        self.send_header("Content-Type",
                         CONTENT_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        # Versioned in its own url, so it can be cached hard.
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        super(http.server.SimpleHTTPRequestHandler, self).end_headers()
        if body:
            self.wfile.write(data)

    def _fetch(self, rest: str, cached: pathlib.Path) -> bool:
        url = UPSTREAM + rest
        sys.stderr.write(f"  cdn miss, fetching {url}\n")
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                payload = response.read()
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            sys.stderr.write(f"  cdn fetch failed: {exc}\n")
            self.send_error(502, f"upstream fetch failed: {exc}")
            return False
        cached.parent.mkdir(parents=True, exist_ok=True)
        # Write beside the target then move, so an interrupted fetch cannot
        # leave a truncated interpreter in the cache to be served forever.
        staging = cached.with_suffix(cached.suffix + ".part")
        staging.write_bytes(payload)
        shutil.move(str(staging), str(cached))
        return True


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    if not (WEB / "index.html").exists():
        sys.stderr.write(
            f"no build at {WEB}. Run:\n"
            f"    PYTHONPATH=src .venv/bin/pygbag --build main.py\n")
        return 1
    with Server(("0.0.0.0", port), Handler) as server:
        print(f"serving {WEB} on http://localhost:{port}")
        print(f"  app bundle: no-store (a rebuild always wins)")
        print(f"  runtime:    proxied from {UPSTREAM}, cached in {CDN_CACHE}")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
