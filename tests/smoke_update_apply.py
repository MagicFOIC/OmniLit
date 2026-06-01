from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
UPDATE_DIR = ROOT / "Update"
if str(UPDATE_DIR) not in sys.path:
    sys.path.insert(0, str(UPDATE_DIR))

import update_core  # noqa: E402


def main() -> int:
    """生成隔离替换夹具并启动真实 helper。参数：无。返回值：进程退出码。"""
    root = ROOT / "smoke_exe" / "apply_test"
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "restarted.txt"
    marker.unlink(missing_ok=True)
    target = root / "DummyLauncher.bat"
    source = root / "DummyLauncher-new.bat"
    target.write_text(f'@echo off\r\necho old>"{root / "old.txt"}"\r\n', encoding="utf-8")
    source.write_text(f'@echo off\r\necho updated>"{marker}"\r\n', encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    sys.frozen = True
    sys.platform = "win32"
    print(
        update_core.apply_update(
            source,
            [str(target)],
            root,
            app_name="DummyLauncher",
            expected_sha256=digest,
            language="en",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
