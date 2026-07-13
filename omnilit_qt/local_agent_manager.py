from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

from .shared_protocol import PROTOCOL_VERSION


LOGGER = logging.getLogger("omnilit.local_agent.lifecycle")


class LocalAgentManager:
    """Own the loopback Local Agent process without exposing a shell command surface."""

    def __init__(self, paths, *, allowed_origins: tuple[str, ...] = ("http://127.0.0.1:4173", "http://localhost:4173"), startup_timeout: float = 5.0, max_restarts: int = 3, executable: Path | None = None, web_root: Path | None = None) -> None:
        self.paths = paths
        self.allowed_origins = tuple(dict.fromkeys(str(origin) for origin in allowed_origins if origin))
        self.startup_timeout = max(0.2, float(startup_timeout))
        self.max_restarts = max(0, int(max_restarts))
        self.executable = Path(executable).resolve() if executable else None
        candidate_web_root = Path(web_root).resolve() if web_root else None
        self.web_root = candidate_web_root if candidate_web_root and (candidate_web_root / "index.html").is_file() else None
        self._lock = threading.RLock()
        self._process: subprocess.Popen[bytes] | None = None
        self._port = 0
        self._access_token = ""
        self._state = "stopped"
        self._detail = ""
        self._restart_count = 0
        self._opener = build_opener(ProxyHandler({}))

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self._port}" if self._port else ""

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def process_id(self) -> int | None:
        process = self._process
        return process.pid if process is not None and process.poll() is None else None

    def status(self) -> dict[str, Any]:
        return {"status": self._state, "detail": self._detail, "endpoint": self.endpoint, "protocolVersion": PROTOCOL_VERSION, "restartCount": self._restart_count, "processId": self.process_id, "webAvailable": self.web_root is not None}

    @staticmethod
    def _available_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    def _command(self) -> list[str]:
        executable = self.executable
        configured = os.getenv("OMNILIT_LOCAL_AGENT_EXECUTABLE", "").strip()
        if executable is None and configured:
            executable = Path(configured).expanduser().resolve()
        if executable is not None:
            if not executable.is_file():
                raise FileNotFoundError("configured Local Agent executable does not exist")
            command = [str(executable)]
        elif getattr(sys, "frozen", False):
            command = [str(Path(sys.executable).resolve()), "--local-agent"]
        else:
            command = [sys.executable, "-m", "services.local_agent"]
        command.extend(["--host", "127.0.0.1", "--port", str(self._port)])
        for origin in self.allowed_origins:
            command.extend(["--origin", origin])
        if self.web_root is not None:
            command.extend(["--web-root", str(self.web_root)])
        return command

    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment["OMNILIT_LOCAL_AGENT_TOKEN"] = self._access_token
        environment["OMNILIT_DATA_DIR"] = str(self.paths.data_root)
        if not getattr(sys, "frozen", False) and self.executable is None:
            source_root = str(Path(__file__).resolve().parent.parent)
            existing = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = source_root + (os.pathsep + existing if existing else "")
        return environment

    def _health(self, timeout: float = 0.5) -> bool:
        if not self.endpoint or not self._access_token:
            return False
        request = Request(self.endpoint + "/v1/health", headers={"Authorization": f"Bearer {self._access_token}", "Accept": "application/json"})
        try:
            with self._opener.open(request, timeout=timeout) as response:
                payload = json.load(response)
        except (OSError, HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return False
        return payload.get("status") == "ready" and payload.get("service") == "omnilit-local-agent" and payload.get("protocolVersion") == PROTOCOL_VERSION

    def start(self) -> bool:
        with self._lock:
            if self._process is not None and self._process.poll() is None and self._health():
                return True
            self._stop_process(timeout=1.0)
            self._port = self._available_port()
            self._access_token = secrets.token_urlsafe(32)
            self._state, self._detail = "starting", ""
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                self._process = subprocess.Popen(
                    self._command(),
                    cwd=str(Path(__file__).resolve().parent.parent),
                    env=self._environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    creationflags=creationflags,
                )
            except (OSError, ValueError) as exc:
                self._state, self._detail, self._process = "failed", "Local Agent process could not be started", None
                LOGGER.warning("local_agent_start_failed reason=%s", type(exc).__name__)
                return False
            deadline = time.monotonic() + self.startup_timeout
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    break
                if self._health():
                    self._state, self._detail = "ready", ""
                    LOGGER.info("local_agent_ready port=%s protocol=%s", self._port, PROTOCOL_VERSION)
                    return True
                time.sleep(0.05)
            self._state, self._detail = "failed", "Local Agent failed its startup health or protocol check"
            self._stop_process(timeout=1.0)
            LOGGER.warning("local_agent_health_failed")
            return False

    def ensure_running(self) -> bool:
        with self._lock:
            if self._process is not None and self._process.poll() is None and self._health():
                return True
            if self._restart_count >= self.max_restarts:
                self._state, self._detail = "failed", "Local Agent restart budget exhausted"
                return False
            self._restart_count += 1
            return self.start()

    def restart(self) -> bool:
        with self._lock:
            if self._restart_count >= self.max_restarts:
                self._state, self._detail = "failed", "Local Agent restart budget exhausted"
                return False
            self._restart_count += 1
            self._stop_process(timeout=1.0)
            return self.start()

    def _stop_process(self, timeout: float) -> None:
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=max(0.1, timeout))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=max(0.1, timeout))

    def shutdown(self, timeout: float = 3.0) -> bool:
        with self._lock:
            process = self._process
            self._stop_process(timeout)
            clean = process is None or process.poll() is not None
            self._state, self._detail = "stopped", ""
            self._port, self._access_token = 0, ""
            return clean
