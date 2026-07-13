from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = Path(__file__).with_name("policy.json")
LICENSE_NAMES = ("license", "licence", "copying", "notice")


def _package_name(package_path: str) -> str:
    return package_path.rsplit("node_modules/", 1)[-1].replace("\\", "/")


def _purl(kind: str, name: str, version: str) -> str:
    encoded_name = "/".join(quote(part, safe="") for part in name.split("/"))
    return f"pkg:{kind}/{encoded_name}@{quote(version, safe='')}"


def _integrity_hash(integrity: str) -> dict[str, str] | None:
    if not integrity or "-" not in integrity:
        return None
    algorithm, encoded = integrity.split("-", 1)
    names = {"sha256": "SHA-256", "sha384": "SHA-384", "sha512": "SHA-512"}
    if algorithm not in names:
        return None
    try:
        content = base64.b64decode(encoded, validate=True).hex()
    except ValueError:
        return None
    return {"alg": names[algorithm], "content": content}


def _license_files(package_directory: Path) -> list[Path]:
    if not package_directory.is_dir():
        return []
    return sorted(
        (path for path in package_directory.iterdir() if path.is_file() and path.name.casefold().startswith(LICENSE_NAMES)),
        key=lambda path: path.name.casefold(),
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def npm_components(root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    if lock.get("lockfileVersion") != 3:
        raise RuntimeError("package-lock.json must use lockfileVersion 3")
    allowed = set(policy["allowedNpmLicenses"])
    components: dict[str, dict[str, Any]] = {}
    notices: list[str] = []
    violations: list[str] = []
    notice_gaps: list[str] = []
    for package_path, metadata in sorted(lock.get("packages", {}).items()):
        if "node_modules/" not in package_path or metadata.get("link") or not metadata.get("version"):
            continue
        name = _package_name(package_path)
        version = str(metadata["version"])
        license_expression = str(metadata.get("license") or "").strip()
        reference = _purl("npm", name, version)
        if not license_expression:
            violations.append(f"npm_missing_license:{name}@{version}")
        elif license_expression not in allowed:
            violations.append(f"npm_disallowed_license:{name}@{version}:{license_expression}")
        package_hash = _integrity_hash(str(metadata.get("integrity") or ""))
        if package_hash is None:
            violations.append(f"npm_missing_integrity:{name}@{version}")
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": reference,
            "name": name,
            "version": version,
            "purl": reference,
            "licenses": [{"expression": license_expression or "NOASSERTION"}],
            "properties": [
                {"name": "omnilit:npmPath", "value": package_path},
                {"name": "omnilit:development", "value": str(bool(metadata.get("dev"))).lower()},
            ],
        }
        if package_hash:
            component["hashes"] = [package_hash]
        if metadata.get("resolved"):
            component["externalReferences"] = [{"type": "distribution", "url": metadata["resolved"]}]
        components.setdefault(reference, component)

        files = _license_files(root / package_path)
        if not files:
            notice_gaps.append(f"npm_missing_license_text:{name}@{version}")
            notices.append(f"===== {name}@{version} ({license_expression or 'NOASSERTION'}) =====\nLicense text was not present in the installed package.\n")
        else:
            text = "\n\n".join(f"--- {path.name} ---\n{_read_text(path)}" for path in files)
            notices.append(f"===== {name}@{version} ({license_expression}) =====\n{text}\n")
    return sorted(components.values(), key=lambda item: item["bom-ref"]), notices, sorted(set(violations)), sorted(set(notice_gaps))


def _exact_requirements(path: Path) -> list[tuple[str, str]]:
    requirements: list[tuple[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^\s;]+)", line)
        if match is None:
            raise RuntimeError(f"Cloud requirement is not exactly pinned: {line}")
        requirements.append((match.group(1), match.group(2)))
    return requirements


def python_components(root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    components: list[dict[str, Any]] = []
    notices: list[str] = []
    violations: list[str] = []
    notice_gaps: list[str] = []
    for name, version in _exact_requirements(root / "services/cloud_api/requirements.in"):
        expression = policy["pythonLicenseExpressions"].get(name.casefold())
        if not expression:
            violations.append(f"python_missing_license_policy:{name}@{version}")
            expression = "NOASSERTION"
        reference = _purl("pypi", name.casefold().replace("_", "-"), version)
        components.append({"type": "library", "bom-ref": reference, "name": name, "version": version, "purl": reference, "licenses": [{"expression": expression}]})
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            violations.append(f"python_not_installed:{name}@{version}")
            notices.append(f"===== {name}@{version} ({expression}) =====\nPackage is not installed; license text could not be collected.\n")
            continue
        if distribution.version != version:
            violations.append(f"python_version_mismatch:{name}:expected={version}:installed={distribution.version}")
        license_paths = sorted(
            (path for path in (distribution.files or ()) if any(part.casefold() == "licenses" for part in path.parts)),
            key=lambda path: str(path).casefold(),
        )
        texts = []
        for relative in license_paths:
            absolute = distribution.locate_file(relative)
            if absolute.is_file():
                texts.append(f"--- {relative.name} ---\n{_read_text(absolute)}")
        if not texts:
            notice_gaps.append(f"python_missing_license_text:{name}@{version}")
            texts.append("License text was not present in the installed distribution.")
        notices.append(f"===== {name}@{version} ({expression}) =====\n" + "\n\n".join(texts) + "\n")
    return components, notices, violations, notice_gaps


def generate(root: Path, output_directory: Path, *, strict: bool, release: bool) -> dict[str, Any]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    npm, npm_notices, violations, npm_notice_gaps = npm_components(root, policy)
    python, python_notices, python_violations, python_notice_gaps = python_components(root, policy)
    violations.extend(python_violations)
    release_blockers = [f"missing_release_file:{path}" for path in policy["releaseRequiredFiles"] if not (root / path).is_file()]
    release_blockers.extend(f"manual_review_required:{item}" for item in policy["manualReleaseReviews"])
    notice_gaps = sorted(set(npm_notice_gaps + python_notice_gaps))
    release_blockers.extend(f"notice_gap:{item}" for item in notice_gaps)

    components = sorted(npm + python, key=lambda item: item["bom-ref"])
    fingerprint = hashlib.sha256("\n".join(item["bom-ref"] for item in components).encode("utf-8")).hexdigest()
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"https://omnilit.invalid/sbom/{fingerprint}")
    sbom = {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "OmniLit", "version": "0.1.0", "bom-ref": "pkg:generic/omnilit@0.1.0"}},
        "components": components,
        "dependencies": [{"ref": "pkg:generic/omnilit@0.1.0", "dependsOn": [item["bom-ref"] for item in components]}],
    }
    report = {
        "status": "blocked" if violations or release_blockers else "ready",
        "componentCount": len(components),
        "npmComponentCount": len(npm),
        "pythonComponentCount": len(python),
        "violations": sorted(set(violations)),
        "releaseBlockers": release_blockers,
        "noticeGaps": notice_gaps,
        "fingerprint": fingerprint,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "omnilit-source.cdx.json").write_text(json.dumps(sbom, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    notices = "OmniLit third-party notices\nGenerated from package-lock.json and the installed Cloud Python distribution.\n\n" + "\n".join(npm_notices + python_notices)
    (output_directory / "THIRD_PARTY_NOTICES.txt").write_text(notices, encoding="utf-8")
    (output_directory / "compliance-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if strict and violations:
        raise RuntimeError("Compliance violations: " + ", ".join(sorted(set(violations))))
    if release and (violations or release_blockers):
        raise RuntimeError("Release compliance is blocked; inspect compliance-report.json")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the OmniLit source SBOM and third-party notices")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/compliance")
    parser.add_argument("--strict", action="store_true", help="Fail on machine-verifiable dependency violations")
    parser.add_argument("--release", action="store_true", help="Also fail on unresolved release and manual review gates")
    args = parser.parse_args()
    report = generate(args.root.resolve(), args.output_dir.resolve(), strict=args.strict, release=args.release)
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
