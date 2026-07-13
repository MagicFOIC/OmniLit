from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
UPDATE_DIRECTORY = ROOT / "Update"
if str(UPDATE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(UPDATE_DIRECTORY))

import update_core  # noqa: E402


class _Response:
    def __init__(self, payload: bytes = b"", *, url: str = "https://example.test/file", length: str | None = None) -> None:
        self.payload = payload
        self.url = url
        self.headers = {} if length is None else {"Content-Length": length}

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def read(self, _size: int = -1) -> bytes:
        return self.payload


class UpdateSecurityTests(unittest.TestCase):
    def test_repository_manifest_signature_is_valid(self) -> None:
        manifest = json.loads((ROOT / "update_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(update_core.verify_manifest_signature(manifest), "omnilit-release-2026-01")

    def test_same_version_hash_difference_cannot_replay_an_update(self) -> None:
        local_hash = hashlib.sha256(b"installed-newer-build").hexdigest()
        old_hash = hashlib.sha256(b"replayed-old-build").hexdigest()
        manifest = update_core.UpdateManifest("1.0.0", "https://example.test/OmniLit.exe", old_hash)
        with patch.object(update_core, "fetch_manifest", return_value=manifest):
            result = update_core.check_for_update("https://example.test/update_manifest.json", "1.0.0", local_hash, language="en")
        self.assertTrue(result.sha256_changed)
        self.assertFalse(result.update_available)
        self.assertIn("version number must be increased", result.status)

    def test_http_sources_and_redirect_downgrades_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "https"):
            update_core.validate_remote_url("http://example.test/update_manifest.json")
        response = _Response(url="http://attacker.test/update_manifest.json")
        with patch.object(update_core.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "https"):
                update_core.fetch_manifest("https://example.test/update_manifest.json")

    def test_manifest_and_artifact_size_limits_fail_closed(self) -> None:
        response = _Response(b"x" * (update_core.MAX_MANIFEST_BYTES + 1), url="https://example.test/update_manifest.json")
        with patch.object(update_core.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "大小限制"):
                update_core.fetch_manifest("https://example.test/update_manifest.json")

        manifest = update_core.UpdateManifest(
            "1.0.1",
            "https://example.test/OmniLit.exe",
            hashlib.sha256(b"release").hexdigest(),
            signature_key_id="omnilit-release-2026-01",
        )
        too_large = _Response(url=manifest.download_url, length=str(update_core.MAX_UPDATE_BYTES + 1))
        with tempfile.TemporaryDirectory() as temporary, patch.object(update_core.urllib.request, "urlopen", return_value=too_large):
            with self.assertRaisesRegex(ValueError, "大小限制"):
                update_core.download_update(manifest, Path(temporary))
            self.assertFalse(list(Path(temporary).glob("*.download")))

    def test_formal_build_scripts_require_platform_signing_and_notarization(self) -> None:
        windows = (ROOT / "build_omnilit_exe.bat").read_text(encoding="utf-8")
        macos = (ROOT / "build_omnilit_macos.sh").read_text(encoding="utf-8")
        self.assertIn("OMNILIT_FORMAL_RELEASE", windows)
        self.assertIn("signtool.exe verify /pa /all", windows)
        self.assertLess(windows.index("signtool.exe sign"), windows.index("postbuild --exe"))
        self.assertIn("codesign --verify --deep --strict", macos)
        self.assertIn("xcrun notarytool submit", macos)
        self.assertIn("xcrun stapler validate", macos)

    def test_tag_workflow_does_not_publish_the_unsigned_smoke_artifact(self) -> None:
        workflow = (ROOT / ".github/workflows/build-macos.yml").read_text(encoding="utf-8")
        self.assertNotIn("tags:", workflow)
        self.assertIn("unsigned-smoke", workflow)

    def test_formal_manifest_signing_cannot_fall_back_to_the_local_development_key(self) -> None:
        import sync_release_metadata

        with patch.dict(os.environ, {"OMNILIT_FORMAL_RELEASE": "1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OMNILIT_UPDATE_SIGNING_KEY_FILE"):
                sync_release_metadata.signing_key_path()


if __name__ == "__main__":
    unittest.main()
