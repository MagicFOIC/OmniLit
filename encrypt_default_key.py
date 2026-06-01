from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from omnilit_qt.support import write_encrypted_key


def main() -> int:
    """生成部署 Key 密文。参数：命令行参数。返回值：进程退出码。"""
    parser = argparse.ArgumentParser(description="Create an encrypted OmniLit default API Key file.")
    parser.add_argument("--output", type=Path, default=Path("Translate/APIKey.enc"))
    args = parser.parse_args()
    api_key = getpass.getpass("DeepSeek API Key: ").strip()
    password = getpass.getpass("Encryption password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    output = write_encrypted_key(args.output, api_key, password)
    print(f"Encrypted key saved to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
