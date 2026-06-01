from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent
APP_NAME = "OmniLit"
MANIFEST_PATH = ROOT / "update_manifest.json"
VERSION_INFO_PATH = ROOT / "version_info.txt"


def load_manifest() -> dict[str, object]:
    """读取发布清单。参数：无。返回值：清单字典。"""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest: dict[str, object]) -> None:
    """写入发布清单。参数：清单字典。返回值：无。"""
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def version_parts(version: str) -> tuple[int, int, int, int]:
    """解析四段版本号。参数：版本文本。返回值：四个整数。"""
    parts = version.strip().split(".")
    if not 1 <= len(parts) <= 4:
        raise ValueError(f"Invalid version: {version}")
    values: list[int] = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"Invalid version: {version}")
        values.append(int(part))
    while len(values) < 4:
        values.append(0)
    return tuple(values[:4])


def download_url_for_version(manifest: dict[str, object], version: str) -> str:
    """生成发布下载地址。参数：清单和版本。返回值：下载 URL。"""
    current = str(manifest.get("download_url") or "").strip()
    filename = f"{APP_NAME}.exe"
    if current:
        parsed = urlsplit(current)
        base_path = parsed.path.rsplit("/", 1)[0]
        path = f"{base_path}/{filename}" if base_path else f"/{filename}"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    return f"https://originchaos.top/omnilit/downloads/{filename}"


def write_version_info(version: str) -> None:
    """写入 Windows 版本资源。参数：版本文本。返回值：无。"""
    major, minor, patch, build = version_parts(version)
    VERSION_INFO_PATH.write_text(
        f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build}),
    prodvers=({major}, {minor}, {patch}, {build}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        "040904B0",
        [
          StringStruct("CompanyName", "magicfoic"),
          StringStruct("FileDescription", "OmniLit unified literature desktop application"),
          StringStruct("FileVersion", "{version}"),
          StringStruct("InternalName", "{APP_NAME}"),
          StringStruct("LegalCopyright", "Copyright (c) 2026 magicfoic. All rights reserved."),
          StringStruct("OriginalFilename", "{APP_NAME}.exe"),
          StringStruct("ProductName", "{APP_NAME}"),
          StringStruct("ProductVersion", "{version}")
        ]
      )
    ]),
    VarFileInfo([VarStruct("Translation", [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    """计算文件摘要。参数：文件路径。返回值：SHA-256。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_history(manifest: dict[str, object], *, sha256: str | None = None) -> None:
    """更新发布历史。参数：清单和可选摘要。返回值：无。"""
    version = str(manifest.get("version") or "").strip()
    notes = str(manifest.get("notes") or "").strip()
    download_url = str(manifest.get("download_url") or "").strip()
    if not version:
        return

    raw_history = manifest.get("history")
    history = raw_history if isinstance(raw_history, list) else []
    entry: dict[str, str] = {
        "version": version,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "notes": notes,
    }
    if sha256:
        entry["sha256"] = sha256
    if download_url:
        entry["download_url"] = download_url

    normalized: list[dict[str, str]] = [entry]
    for item in history:
        if not isinstance(item, dict):
            continue
        item_version = str(item.get("version") or "").strip()
        if item_version == version:
            continue
        normalized.append(
            {
                key: str(value)
                for key, value in item.items()
                if key in {"version", "date", "published_at", "notes", "sha256", "download_url"} and value is not None
            }
        )
        if len(normalized) >= 20:
            break
    manifest["history"] = normalized


def prebuild() -> str:
    """执行构建前同步。参数：无。返回值：版本文本。"""
    manifest = load_manifest()
    version = str(manifest.get("version") or "").strip()
    if not version:
        raise ValueError("update_manifest.json must contain a non-empty version")
    version_parts(version)
    manifest["download_url"] = download_url_for_version(manifest, version)
    update_history(manifest)
    save_manifest(manifest)
    write_version_info(version)
    return version


def postbuild(exe_path: Path) -> str:
    """执行构建后同步。参数：EXE 路径。返回值：SHA-256。"""
    manifest = load_manifest()
    version = str(manifest.get("version") or "").strip()
    if not exe_path.exists():
        raise FileNotFoundError(exe_path)
    manifest["download_url"] = download_url_for_version(manifest, version)
    manifest["sha256"] = sha256_file(exe_path)
    update_history(manifest, sha256=str(manifest["sha256"]))
    save_manifest(manifest)
    return str(manifest["sha256"])


def main() -> None:
    """处理发布同步命令。参数：命令行参数。返回值：无。"""
    parser = argparse.ArgumentParser(description="Synchronize OmniLit release metadata.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prebuild")
    subparsers.add_parser("print-version")
    postbuild_parser = subparsers.add_parser("postbuild")
    postbuild_parser.add_argument("--exe", required=True, type=Path)
    args = parser.parse_args()

    if args.command == "prebuild":
        print(prebuild())
    elif args.command == "print-version":
        print(str(load_manifest().get("version") or "").strip())
    elif args.command == "postbuild":
        print(postbuild(args.exe.resolve()))


if __name__ == "__main__":
    main()
