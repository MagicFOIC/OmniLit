from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .pdf_extraction_settings import redact_sensitive_text


RUNTIME_VERSION = 1


class ParserRuntimeManager:
    def __init__(self, app_data_dir: Path | None = None) -> None:
        self.root = Path(app_data_dir) if app_data_dir is not None else default_runtime_root()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.root = Path(tempfile.gettempdir()) / "OmniLit" / "parser_runtimes"
            self.root.mkdir(parents=True, exist_ok=True)

    def get_status(self) -> dict[str, Any]:
        manifest = self._read_manifest()
        manifest.setdefault("version", RUNTIME_VERSION)
        manifest.setdefault("runtimes", {})
        for name in ("mineru", "paddleocr_vl"):
            manifest["runtimes"].setdefault(name, self._default_runtime_status(name))
        return manifest

    def find_system_command(self, name: str) -> str | None:
        value = shutil.which(name)
        return str(value) if value else None

    def ensure_mineru_runtime(self, progress_callback: Callable[[str, int, str], None] | None = None) -> dict[str, Any]:
        available = self.check_mineru_available()
        if available.get("available"):
            return available

        runtime_dir = self.root / "mineru"
        venv_dir = runtime_dir / ".venv"
        logs_dir = runtime_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "mineru_install.log"

        def progress(message: str, percent: int) -> None:
            if progress_callback:
                progress_callback("mineru", percent, message)

        try:
            progress("正在创建 MinerU 独立运行环境...", 10)
            runtime_dir.mkdir(parents=True, exist_ok=True)
            if not self._python_for_venv(venv_dir).exists():
                self._run([sys.executable, "-m", "venv", str(venv_dir)], log_path)

            python = self._python_for_venv(venv_dir)
            progress("正在升级 pip...", 35)
            self._run([str(python), "-V"], log_path)
            self._run([str(python), "-m", "pip", "install", "-U", "pip"], log_path)
            self._run([str(python), "-m", "pip", "install", "uv"], log_path)
            progress("正在安装 MinerU，首次使用需要下载依赖...", 65)
            self._run([str(python), "-m", "uv", "pip", "install", "-U", "mineru[all]"], log_path)

            command = self._command_for_venv(venv_dir, "mineru")
            status = {
                "available": True,
                "installable": False,
                "status": "ready",
                "python": str(python),
                "command": str(command),
                "message": "MinerU 深度解析组件已初始化。",
            }
            self._update_runtime("mineru", status | {"installedAt": _now(), "lastError": ""})
            progress("MinerU 初始化完成。", 100)
            return status
        except Exception as exc:
            message = "MinerU 自动初始化失败，已回退到 PyMuPDF。可检查网络或 pip 源。"
            detail = redact_sensitive_text(str(exc))
            self._update_runtime("mineru", {"status": "failed", "lastError": detail, "lastCheckedAt": _now()})
            _append_log(log_path, f"\nERROR\n{message}\n{detail}\n")
            progress(message, 100)
            return {"available": False, "installable": True, "status": "failed", "python": "", "command": "", "message": message, "lastError": detail}

    def check_mineru_available(self) -> dict[str, Any]:
        command = os.environ.get("OMNILIT_MINERU_COMMAND", "").strip()
        if command and _command_exists(command):
            return {"available": True, "installable": False, "status": "ready", "command": command, "python": "", "message": "MinerU CLI 可用。"}

        manifest_status = self.get_status()["runtimes"].get("mineru", {})
        managed_python = str(manifest_status.get("python") or "")
        managed_command = str(manifest_status.get("command") or "")
        if managed_python and Path(managed_python).exists():
            return {
                "available": True,
                "installable": False,
                "status": "ready",
                "python": managed_python,
                "command": managed_command,
                "message": "MinerU 托管运行时可用。",
            }

        runtime_dir = self.root / "mineru" / ".venv"
        python = self._python_for_venv(runtime_dir)
        command_path = self._command_for_venv(runtime_dir, "mineru")
        if python.exists():
            return {
                "available": True,
                "installable": False,
                "status": "ready",
                "python": str(python),
                "command": str(command_path),
                "message": "MinerU 托管运行时可用。",
            }

        system = self.find_system_command("mineru")
        if system:
            return {"available": True, "installable": False, "status": "ready", "python": "", "command": system, "message": "PATH 中 MinerU 可用。"}

        return {
            "available": False,
            "installable": True,
            "status": "installable",
            "python": "",
            "command": "",
            "message": "MinerU 深度解析组件未安装，可自动初始化。",
        }

    def check_paddleocr_vl_available(self) -> dict[str, Any]:
        explicit_url = os.environ.get("OMNILIT_PADDLEOCR_VL_URL", "").strip()
        for url in [explicit_url, "http://127.0.0.1:8118/v1"]:
            if url and _service_reachable(url):
                return {
                    "available": True,
                    "installable": False,
                    "status": "service",
                    "serviceUrl": url,
                    "python": os.environ.get("OMNILIT_PADDLEOCR_VL_PYTHON", "").strip(),
                    "command": "",
                    "message": "PaddleOCR-VL 服务可用。",
                }

        manifest_status = self.get_status()["runtimes"].get("paddleocr_vl", {})
        managed_python = str(manifest_status.get("python") or "")
        if managed_python and Path(managed_python).exists():
            return {
                "available": True,
                "installable": False,
                "status": "managed",
                "python": managed_python,
                "serviceUrl": "",
                "command": "",
                "message": "PaddleOCR-VL 独立运行环境可用。",
            }

        command = self.find_system_command("paddleocr")
        if command:
            return {
                "available": True,
                "installable": False,
                "status": "cli",
                "python": "",
                "serviceUrl": "",
                "command": command,
                "message": "PATH 中 paddleocr 命令可用。",
            }

        docker = self.find_system_command("docker")
        if docker:
            return {
                "available": False,
                "installable": True,
                "status": "docker_installable",
                "python": "",
                "serviceUrl": "",
                "command": docker,
                "message": "可通过 Docker 初始化 PaddleOCR-VL 服务。",
            }

        return {
            "available": False,
            "installable": False,
            "status": "not_initialized",
            "python": "",
            "serviceUrl": "",
            "command": "",
            "message": "PaddleOCR-VL 高精度引擎未初始化，可使用 MinerU 或 PyMuPDF 回退。",
        }

    def sanitize_log(self, text: str) -> str:
        return redact_sensitive_text(text)

    def _run(self, cmd: list[str], log_path: Path) -> None:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=1800)
        _append_log(log_path, f"$ {' '.join(cmd)}\nSTDOUT\n{self.sanitize_log(completed.stdout)}\nSTDERR\n{self.sanitize_log(completed.stderr)}\n")
        if completed.returncode != 0:
            raise RuntimeError(f"command failed with exit code {completed.returncode}: {completed.stderr or completed.stdout}")

    def _read_manifest(self) -> dict[str, Any]:
        path = self.root / "manifest.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        path = self.root / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_runtime(self, name: str, values: dict[str, Any]) -> None:
        manifest = self.get_status()
        current = dict(manifest["runtimes"].get(name) or self._default_runtime_status(name))
        current.update(values)
        current["lastCheckedAt"] = _now()
        manifest["runtimes"][name] = current
        self._write_manifest(manifest)
        runtime_dir = self.root / name
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "status.json").write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _default_runtime_status(name: str) -> dict[str, Any]:
        return {"status": "not_installed", "python": "", "command": "", "serviceUrl": "", "installedAt": "", "lastCheckedAt": "", "lastError": ""}

    @staticmethod
    def _python_for_venv(venv_dir: Path) -> Path:
        return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    @staticmethod
    def _command_for_venv(venv_dir: Path, command: str) -> Path:
        suffix = ".exe" if os.name == "nt" else ""
        return venv_dir / ("Scripts" if os.name == "nt" else "bin") / f"{command}{suffix}"


def default_runtime_root() -> Path:
    if os.name == "nt":
        try:
            fallback_home = Path.home() / "AppData" / "Local"
        except RuntimeError:
            fallback_home = Path(tempfile.gettempdir())
        base = Path(os.environ.get("LOCALAPPDATA") or fallback_home)
        return base / "OmniLit" / "parser_runtimes"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OmniLit" / "parser_runtimes"
    return Path.home() / ".local" / "share" / "OmniLit" / "parser_runtimes"


def _command_exists(command: str) -> bool:
    path = Path(command)
    if path.parent != Path("."):
        return path.exists()
    return shutil.which(command) is not None


def _service_reachable(url: str) -> bool:
    try:
        host, port = _host_port(url)
        with socket.create_connection((host, port), timeout=0.35):
            return True
    except OSError:
        return False


def _host_port(url: str) -> tuple[str, int]:
    text = str(url or "").split("://", 1)[-1]
    host_port = text.split("/", 1)[0]
    if ":" in host_port:
        host, port = host_port.rsplit(":", 1)
        return host or "127.0.0.1", int(port)
    return host_port or "127.0.0.1", 443 if str(url).startswith("https://") else 80


def _append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
