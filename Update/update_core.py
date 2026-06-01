from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


NETWORK_TIMEOUT_SECONDS = 15
CHUNK_SIZE = 1024 * 256
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MANIFEST_SIGNATURE_ALGORITHM = "ed25519"
TRUSTED_MANIFEST_PUBLIC_KEYS = {
    "omnilit-release-2026-01": "94qWrgdq+X8jvd81rRCztoPJ97Umclz8P4iN2XhhEuM=",
}


ProgressCallback = Callable[[int, int, str], None]


def canonical_manifest_bytes(data: dict) -> bytes:
    """Return stable bytes for signing all manifest fields except the signature."""
    unsigned = {key: value for key, value in data.items() if key != "signature"}
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_manifest_signature(data: dict) -> str:
    """Verify the manifest against the embedded Ed25519 release keys."""
    signature = data.get("signature")
    if not isinstance(signature, dict):
        raise ValueError("Update manifest is unsigned; refusing an untrusted release.")
    algorithm = str(signature.get("algorithm") or "").strip().lower()
    if algorithm != MANIFEST_SIGNATURE_ALGORITHM:
        raise ValueError(f"Unsupported update manifest signature algorithm: {algorithm or 'missing'}.")
    key_id = str(signature.get("key_id") or "").strip()
    public_key_text = TRUSTED_MANIFEST_PUBLIC_KEYS.get(key_id)
    if not public_key_text:
        raise ValueError(f"Update manifest uses an untrusted signing key: {key_id or 'missing'}.")
    signature_text = str(signature.get("value") or "").strip()
    try:
        public_key_bytes = base64.b64decode(public_key_text, validate=True)
        signature_bytes = base64.b64decode(signature_text, validate=True)
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes,
            canonical_manifest_bytes(data),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("Update manifest Ed25519 signature verification failed.") from exc
    return key_id


def validate_manifest_trust(manifest: "UpdateManifest") -> None:
    """Reject manifest objects that did not pass embedded-key verification."""
    if manifest.signature_key_id not in TRUSTED_MANIFEST_PUBLIC_KEYS:
        raise ValueError("Update manifest is not trusted; refusing to download the release.")


def localized(language: str, zh: str, en: str) -> str:
    """按任务语言选择文本。参数：语言和中英文。返回值：当前语言文本。"""
    return en if language == "en" else zh


@dataclass(frozen=True)
class UpdateManifest:
    """描述远程更新清单。"""
    version: str
    download_url: str
    sha256: str = ""
    notes: str = ""
    mandatory: bool = False
    history: tuple[dict[str, str], ...] = ()
    signature_key_id: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "UpdateManifest":
        """解析清单。参数：JSON 字典。返回值：清单对象。"""
        signature_key_id = verify_manifest_signature(data)
        version = str(data.get("version") or "").strip()
        download_url = str(data.get("download_url") or "").strip()
        if not version or not download_url:
            raise ValueError("版本清单缺少 version 或 download_url。")
        sha256 = validate_sha256(str(data.get("sha256") or ""))

        history_items: list[dict[str, str]] = []
        raw_history = data.get("history")
        if isinstance(raw_history, list):
            for item in raw_history:
                if not isinstance(item, dict):
                    continue
                item_version = str(item.get("version") or "").strip()
                item_notes = str(item.get("notes") or "").strip()
                item_date = str(item.get("date") or item.get("published_at") or "").strip()
                if not item_version and not item_notes:
                    continue
                history_items.append(
                    {"version": item_version, "date": item_date, "notes": item_notes}
                )

        return cls(
            version=version,
            download_url=download_url,
            sha256=sha256,
            notes=str(data.get("notes") or "").strip(),
            mandatory=bool(data.get("mandatory")),
            history=tuple(history_items),
            signature_key_id=signature_key_id,
        )

    def formatted_notes(self, limit: int | None = None) -> str:
        """格式化版本记录。参数：可选条数限制。返回值：多行文本。"""
        lines: list[str] = []
        seen_releases: set[tuple[str, str]] = set()
        has_current_history = any(
            item.get("version", "").strip() == self.version
            and item.get("notes", "").strip() == self.notes
            for item in self.history
        )
        if self.notes and not has_current_history:
            lines.append(f"{self.version}: {self.notes}")
            seen_releases.add((self.version, self.notes))

        for item in self.history:
            item_version = item.get("version", "").strip()
            item_notes = item.get("notes", "").strip()
            item_date = item.get("date", "").strip()
            if not item_notes:
                continue
            release_key = (item_version, item_notes)
            if release_key in seen_releases:
                continue
            prefix = item_version or "unknown"
            if item_date:
                prefix = f"{prefix} ({item_date})"
            lines.append(f"{prefix}: {item_notes}")
            seen_releases.add(release_key)
            if limit is not None and len(lines) >= limit:
                break
        return "\n".join(lines)


@dataclass(frozen=True)
class UpdateCheckResult:
    """描述版本比较结果。"""
    manifest: UpdateManifest | None
    is_newer: bool
    sha256_changed: bool
    status: str

    @property
    def update_available(self) -> bool:
        """返回是否需要更新。参数：无。返回值：版本或摘要是否变化。"""
        return self.is_newer or self.sha256_changed


def version_tuple(version: str) -> tuple[int, ...]:
    """解析可比较版本号。参数：版本文本。返回值：整数元组。"""
    values: list[int] = []
    for part in version.replace("-", ".").split("."):
        digits = ""
        for char in part:
            if char.isdigit():
                digits += char
            else:
                break
        values.append(int(digits or 0))
    return tuple(values)


def validate_remote_url(url: str, *, label: str = "URL") -> str:
    """验证远程 URL。参数：URL 和字段名。返回值：规范文本。"""
    value = url.strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} 必须是 http 或 https 地址。")
    return value


def validate_sha256(value: str) -> str:
    """验证 SHA-256。参数：摘要文本。返回值：规范摘要。"""
    digest = value.strip().lower()
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError("缺少有效的更新文件 SHA256，已拒绝更新。")
    return digest


def _cache_busted_url(url: str, key: str, value: str) -> str:
    """为远程请求添加缓存隔离参数。参数：URL、键和值。返回值：新 URL。"""
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append((key, value))
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
    )


def _remote_request(url: str) -> urllib.request.Request:
    """创建禁用缓存的远程请求。参数：URL。返回值：请求对象。"""
    return urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})


def fetch_manifest(url: str, timeout: int = NETWORK_TIMEOUT_SECONDS) -> UpdateManifest:
    """下载更新清单。参数：URL 和超时。返回值：清单对象。"""
    manifest_url = validate_remote_url(url, label="更新地址")
    manifest_url = _cache_busted_url(manifest_url, "_omnilit_check", str(time.time_ns()))
    with urllib.request.urlopen(_remote_request(manifest_url), timeout=timeout) as response:
        payload = response.read(1024 * 1024)
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("版本清单必须是 JSON 对象。")
    return UpdateManifest.from_dict(data)


def check_for_update(url: str, current_version: str, current_sha256: str = "", language: str = "zh") -> UpdateCheckResult:
    """检查更新。参数：清单地址、当前版本、当前摘要和语言。返回值：检查结果。"""
    manifest = fetch_manifest(url)
    is_newer = version_tuple(manifest.version) > version_tuple(current_version)
    same_version = version_tuple(manifest.version) == version_tuple(current_version)
    local_sha256 = current_sha256.strip().lower()
    sha256_changed = bool(same_version and SHA256_PATTERN.fullmatch(local_sha256) and manifest.sha256 != local_sha256)
    if is_newer:
        status = localized(language, f"发现可用版本：{manifest.version}。", f"Version {manifest.version} is available.")
    elif sha256_changed:
        status = localized(language, f"检测到服务器发布文件已更新：{manifest.version}（SHA256 已变化）。", f"The server release file changed for {manifest.version} (SHA256 changed).")
    else:
        status = localized(language, "已是最新版本。", "You already have the latest version.")
    return UpdateCheckResult(manifest=manifest, is_newer=is_newer, sha256_changed=sha256_changed, status=status)


def sha256_file(path: Path) -> str:
    """计算文件摘要。参数：文件路径。返回值：SHA-256。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected_sha256: str) -> bool:
    """校验文件摘要。参数：文件和期望摘要。返回值：是否匹配。"""
    expected = expected_sha256.strip().lower()
    if not expected:
        return True
    if not SHA256_PATTERN.fullmatch(expected):
        raise ValueError("缺少有效的更新文件 SHA256，已拒绝替换当前程序。")
    actual = sha256_file(path)
    return actual == expected


def download_update(
    manifest: UpdateManifest,
    target_dir: Path,
    progress_callback: ProgressCallback | None = None,
    timeout: int = NETWORK_TIMEOUT_SECONDS,
    language: str = "zh",
    stop_callback: Callable[[], bool] | None = None,
) -> Path:
    """下载并校验更新包。参数：清单、目录、进度回调、超时和语言。返回值：下载文件路径。"""
    validate_manifest_trust(manifest)
    download_url = validate_remote_url(manifest.download_url, label="下载 URL")
    expected_sha256 = validate_sha256(manifest.sha256)
    request_url = _cache_busted_url(download_url, "_omnilit_sha256", expected_sha256)
    target_dir.mkdir(parents=True, exist_ok=True)
    parsed = urllib.parse.urlparse(download_url)
    suffix = Path(parsed.path).suffix or ".exe"
    final_path = target_dir / f"OmniLit-{manifest.version}{suffix}"
    temporary_path = final_path.with_suffix(final_path.suffix + ".download")

    def raise_if_stopped() -> None:
        if stop_callback and stop_callback():
            raise RuntimeError(localized(language, "更新下载已取消。", "Update download cancelled."))

    try:
        raise_if_stopped()
        with urllib.request.urlopen(_remote_request(request_url), timeout=timeout) as response:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            if progress_callback:
                progress_callback(downloaded, total, localized(language, f"准备下载 {manifest.version}", f"Preparing download {manifest.version}"))
            with temporary_path.open("wb") as handle:
                while True:
                    raise_if_stopped()
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total, localized(language, f"正在下载 {manifest.version}", f"Downloading {manifest.version}"))

        raise_if_stopped()
        if not verify_sha256(temporary_path, expected_sha256):
            raise ValueError("安装包 SHA256 校验失败。")
        temporary_path.replace(final_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    if progress_callback:
        progress_callback(final_path.stat().st_size, final_path.stat().st_size, localized(language, "下载完成", "Download complete"))
    return final_path


def apply_update(
    downloaded_path: Path,
    current_launcher: list[str],
    data_dir: Path,
    app_name: str = "OmniLit",
    expected_sha256: str = "",
    language: str = "zh",
) -> str:
    """生成 Windows 替换脚本。参数：下载文件、启动命令、数据目录、应用名、摘要和语言。返回值：状态文本。"""
    source_exe = downloaded_path.resolve()
    if not source_exe.exists():
        raise FileNotFoundError(source_exe)

    if not getattr(sys, "frozen", False) or not sys.platform.startswith("win"):
        _open_parent_folder(source_exe)
        raise RuntimeError("自动覆盖当前程序目前仅支持 Windows 打包版。")

    current_exe = Path(current_launcher[0]).resolve()
    if not current_exe.exists():
        raise FileNotFoundError(current_exe)
    if source_exe == current_exe:
        raise RuntimeError("更新源文件不能与当前程序文件相同。")
    if expected_sha256 and not verify_sha256(source_exe, expected_sha256):
        raise ValueError("更新文件 SHA256 校验失败，已拒绝替换当前程序。")

    cleanup_updates_dir = data_dir / "updates"
    script = data_dir / f"apply_{app_name.lower()}_update.bat"
    log_file = data_dir / f"apply_{app_name.lower()}_update.log"
    script.parent.mkdir(parents=True, exist_ok=True)
    try:
        script.unlink(missing_ok=True)
    except OSError:
        pass

    script.write_text(
        f"""@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
set "PID={os.getpid()}"
set "SOURCE={source_exe}"
set "TARGET={current_exe}"
set "TARGET_NEW={current_exe}.new"
set "TARGET_OLD={current_exe}.old"
set "CLEANUP_UPDATES={cleanup_updates_dir}"
set "LOG={log_file}"
set "SELF=%~f0"
set "EXPECTED_SHA256={expected_sha256.strip().lower()}"
set "WAIT_SECONDS=0"

>"%LOG%" echo [OmniLit] applying update
>>"%LOG%" echo SOURCE=%SOURCE%
>>"%LOG%" echo TARGET=%TARGET%

:wait_process
tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  set /a WAIT_SECONDS+=1
  if !WAIT_SECONDS! GEQ 75 (
    >>"%LOG%" echo Process did not exit after termination request. Aborting update.
    exit /b 1
  )
  if !WAIT_SECONDS! GEQ 45 (
    >>"%LOG%" echo Process did not exit within 45 seconds. Terminating PID %PID%.
    taskkill /PID %PID% /T /F >>"%LOG%" 2>&1
    timeout /t 2 /nobreak >nul
  )
  goto wait_process
)

if exist "%TARGET_NEW%" del /f /q "%TARGET_NEW%" >>"%LOG%" 2>&1
copy /y "%SOURCE%" "%TARGET_NEW%" >>"%LOG%" 2>&1
if errorlevel 1 (
  timeout /t 2 /nobreak >nul
  copy /y "%SOURCE%" "%TARGET_NEW%" >>"%LOG%" 2>&1
)
if errorlevel 1 (
  >>"%LOG%" echo Copy to staging file failed.
  exit /b 1
)
if not "%EXPECTED_SHA256%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $env:TARGET_NEW).Hash.ToLowerInvariant(); if ($hash -ne $env:EXPECTED_SHA256) {{ throw ('Staged file SHA256 mismatch: ' + $hash) }}" >>"%LOG%" 2>&1
  if errorlevel 1 (
    if exist "%TARGET_NEW%" del /f /q "%TARGET_NEW%" >>"%LOG%" 2>&1
    >>"%LOG%" echo Staged file verification failed.
    exit /b 1
  )
)
if exist "%TARGET_OLD%" del /f /q "%TARGET_OLD%" >>"%LOG%" 2>&1
move /y "%TARGET%" "%TARGET_OLD%" >>"%LOG%" 2>&1
if errorlevel 1 (
  >>"%LOG%" echo Could not move current executable to backup.
  if exist "%TARGET_NEW%" del /f /q "%TARGET_NEW%" >>"%LOG%" 2>&1
  exit /b 1
)
move /y "%TARGET_NEW%" "%TARGET%" >>"%LOG%" 2>&1
if errorlevel 1 (
  >>"%LOG%" echo Could not move staged executable into place. Rolling back.
  if exist "%TARGET%" del /f /q "%TARGET%" >>"%LOG%" 2>&1
  move /y "%TARGET_OLD%" "%TARGET%" >>"%LOG%" 2>&1
  exit /b 1
)
if not "%EXPECTED_SHA256%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $env:TARGET).Hash.ToLowerInvariant(); if ($hash -ne $env:EXPECTED_SHA256) {{ throw ('Target SHA256 mismatch after replace: ' + $hash) }}" >>"%LOG%" 2>&1
  if errorlevel 1 (
    >>"%LOG%" echo Final executable verification failed. Rolling back.
    if exist "%TARGET%" del /f /q "%TARGET%" >>"%LOG%" 2>&1
    move /y "%TARGET_OLD%" "%TARGET%" >>"%LOG%" 2>&1
    exit /b 1
  )
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$target=$env:TARGET; $targetDir=Split-Path -Parent $target; $env:PYINSTALLER_RESET_ENVIRONMENT='1'; Get-ChildItem Env: | Where-Object {{ $_.Name -eq '_MEIPASS2' -or $_.Name -like '_PYI*' }} | Remove-Item -ErrorAction SilentlyContinue; Start-Process -FilePath $target -WorkingDirectory $targetDir" >>"%LOG%" 2>&1
if errorlevel 1 (
  set "PYINSTALLER_RESET_ENVIRONMENT=1"
  set "_MEIPASS2="
  set "_PYI_APPLICATION_HOME_DIR="
  set "_PYI_PARENT_PROCESS_LEVEL="
  set "_PYI_ARCHIVE_FILE="
  start "" "%TARGET%"
)
if exist "%TARGET_OLD%" del /f /q "%TARGET_OLD%" >>"%LOG%" 2>&1
if exist "%CLEANUP_UPDATES%" rmdir /s /q "%CLEANUP_UPDATES%" >>"%LOG%" 2>&1
>>"%LOG%" echo Update helper finished.
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2; Remove-Item -LiteralPath $env:SELF,$env:LOG -Force -ErrorAction SilentlyContinue"
exit /b 0
""",
        encoding="utf-8-sig",
    )

    update_env = os.environ.copy()
    update_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for env_name in list(update_env):
        if env_name == "_MEIPASS2" or env_name.startswith("_PYI"):
            update_env.pop(env_name, None)
    meipass = str(getattr(sys, "_MEIPASS", "") or "")
    if meipass:
        current_path = update_env.get("PATH", "")
        update_env["PATH"] = os.pathsep.join(
            item for item in current_path.split(os.pathsep) if item and not item.startswith(meipass)
        )

    try:
        import ctypes

        ctypes.windll.kernel32.SetDllDirectoryW(None)
    except Exception:
        pass

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    subprocess.Popen(
        ["cmd.exe", "/d", "/c", str(script)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        cwd=str(data_dir),
        env=update_env,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )
    return localized(language, "正在关闭当前程序并应用更新...", "Closing the current app and applying the update...")


def _open_parent_folder(path: Path) -> None:
    """打开文件父目录。参数：文件路径。返回值：无。"""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path.parent))  # type: ignore[attr-defined]
        else:
            opener = shutil.which("open") or shutil.which("xdg-open")
            if not opener:
                raise RuntimeError("未找到系统打开命令。")
            subprocess.Popen([opener, str(path.parent)])
    except Exception:
        pass
