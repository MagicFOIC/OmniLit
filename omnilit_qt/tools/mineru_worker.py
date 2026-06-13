from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from omnilit_qt.pdf_extraction_settings import redact_sensitive_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MinerU outside the OmniLit main environment.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--backend", default="pipeline")
    parser.add_argument("--command", default="mineru")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    raw_dir = output_dir / "mineru_raw"
    log_path = output_dir / "mineru.log"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    cmd = [args.command, "-p", str(input_path), "-o", str(raw_dir)]
    if args.backend and args.backend != "auto":
        cmd.extend(["-b", args.backend])

    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    log_path.write_text(
        f"COMMAND\n{' '.join(cmd)}\n\nSTDOUT\n{redact_sensitive_text(completed.stdout)}\n\nSTDERR\n{redact_sensitive_text(completed.stderr)}\n",
        encoding="utf-8",
    )
    manifest = _manifest(raw_dir, log_path)
    (output_dir / "mineru_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(completed.returncode)


def _manifest(raw_dir: Path, log_path: Path) -> dict[str, object]:
    return {
        "markdown_files": [str(path) for path in sorted(raw_dir.rglob("*.md"))],
        "json_files": [str(path) for path in sorted(raw_dir.rglob("*.json"))],
        "image_files": [str(path) for path in sorted(raw_dir.rglob("*")) if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}],
        "html_files": [str(path) for path in sorted(raw_dir.rglob("*.html"))],
        "log_file": str(log_path),
    }


if __name__ == "__main__":
    raise SystemExit(main())
