from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from omnilit_qt.support import DEFAULT_KEY_AUTO_PASSWORD, load_encrypted_key, write_encrypted_key


def main() -> int:
    """生成部署 Key 密文。参数：命令行参数。返回值：进程退出码。"""
    parser = argparse.ArgumentParser(description="Create an encrypted OmniLit default API Key file.")
    parser.add_argument("--output", type=Path, default=Path("Translate/APIKey.enc"))
    parser.add_argument("--prompt-password", action="store_true", help="Ask for a custom encryption password instead of using the app-managed deployment password.")
    parser.add_argument("--migrate-from-password", action="store_true", help="Decrypt an existing APIKey.enc with its old password and rewrite it for one-click app unlock.")
    args = parser.parse_args()
    if args.migrate_from_password:
        old_password = getpass.getpass("Existing APIKey.enc password: ")
        api_key = load_encrypted_key(args.output, old_password)
    else:
        api_key = getpass.getpass("DeepSeek API Key: ").strip()
    if args.prompt_password:
        password = getpass.getpass("Encryption password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match.")
    else:
        password = DEFAULT_KEY_AUTO_PASSWORD
    output = write_encrypted_key(args.output, api_key, password)
    print(f"Encrypted key saved to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
