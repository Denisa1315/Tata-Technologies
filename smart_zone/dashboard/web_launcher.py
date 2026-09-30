"""Launcher for the exported AI Studio simulation living in simulation/
(sibling to smart_zone/, at the repo root). Display/demo-tooling only --
this module treats simulation/ as a completely opaque asset to launch, never
edits anything inside it, and has nothing to do with detection or risk
decisions.

simulation/ is a real React 19 + Vite + TypeScript app (index.html loads
/src/main.tsx as an ES module) -- it needs Vite's own dev server to
transpile/bundle that, so this launches `npm run dev` (the script already
defined in simulation/package.json) as a background subprocess, waits
(bounded, in a background thread) for its port to come up, then opens the
default browser to it. Nothing here runs Python's http.server directly
against raw .tsx source, since a browser can't execute that.

Started only once per process: a second call while the server is already
starting or running is a no-op (see WebSimLauncher.launch's guard), so
repeatedly pressing 'w' doesn't spawn duplicate dev servers or open extra
browser tabs on every press.
"""

from __future__ import annotations

import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

SIMULATION_DIR = Path(__file__).resolve().parent.parent.parent / "simulation"
ENTRY_FILE = SIMULATION_DIR / "index.html"

DEV_SERVER_PORT = 3000
DEV_SERVER_URL = f"http://localhost:{DEV_SERVER_PORT}"
PORT_WAIT_TIMEOUT_S = 20.0
PORT_POLL_INTERVAL_S = 0.3


def _port_is_open(port: int, host: str = "localhost", timeout_s: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


class WebSimLauncher:
    """Owns at most one `npm run dev` subprocess for the whole app run.
    launch() is safe to call repeatedly (e.g. once per 'w' keypress) --
    only the first call actually starts anything; later calls are no-ops
    while that server is starting or already running."""

    def __init__(
        self,
        simulation_dir: Path = SIMULATION_DIR,
        port: int = DEV_SERVER_PORT,
    ) -> None:
        self._simulation_dir = simulation_dir
        self._entry_file = simulation_dir / "index.html"
        self._port = port
        self._url = f"http://localhost:{port}"

        self._lock = threading.Lock()
        self._started = False
        self._process: subprocess.Popen | None = None

    def launch(self) -> None:
        """Call from the main loop on a 'w' keypress. Returns immediately
        (does not block the caller) -- starting the dev server and waiting
        for it to come up happens on a background thread; only the guard
        check and subprocess.Popen() call (both effectively instant) run
        on the calling thread."""
        with self._lock:
            if self._started:
                # Already starting or running -- do nothing, so repeated
                # 'w' presses don't spawn duplicate servers/tabs.
                return
            self._started = True

        if not self._entry_file.exists():
            print(
                f"[web_launcher] Simulation entry file not found at {self._entry_file}. "
                "Nothing to launch -- check that the simulation/ folder exists at the "
                "repo root, sibling to smart_zone/, with an index.html inside it."
            )
            with self._lock:
                self._started = False  # allow a retry later (e.g. if the folder appears)
            return

        if not (self._simulation_dir / "package.json").exists():
            print(
                f"[web_launcher] {self._simulation_dir} has an index.html but no "
                "package.json -- can't run `npm run dev` against it."
            )
            with self._lock:
                self._started = False
            return

        threading.Thread(target=self._start_and_open, daemon=True).start()

    def _start_and_open(self) -> None:
        try:
            self._process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(self._simulation_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, FileNotFoundError) as e:
            print(f"[web_launcher] Failed to start `npm run dev` in {self._simulation_dir}: {e}")
            with self._lock:
                self._started = False
            return

        print(f"[web_launcher] Starting simulation dev server in {self._simulation_dir} "
              f"(waiting up to {PORT_WAIT_TIMEOUT_S:.0f}s for {self._url})...")

        deadline = time.monotonic() + PORT_WAIT_TIMEOUT_S
        while time.monotonic() < deadline:
            if _port_is_open(self._port):
                print(f"[web_launcher] Simulation ready -- opening {self._url}")
                webbrowser.open(self._url)
                return
            if self._process.poll() is not None:
                print(f"[web_launcher] `npm run dev` exited early (code {self._process.returncode}) "
                      "before the server came up.")
                with self._lock:
                    self._started = False
                return
            time.sleep(PORT_POLL_INTERVAL_S)

        print(f"[web_launcher] Timed out waiting for {self._url} after {PORT_WAIT_TIMEOUT_S:.0f}s. "
              "The dev server may still be starting -- check your terminal/npm output, "
              "or open the URL manually once it's up.")

    def close(self) -> None:
        """Stop the dev server subprocess, if one was started. Call this
        from app.py's shutdown path so a quit doesn't leave an orphaned
        `npm run dev` process running."""
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
