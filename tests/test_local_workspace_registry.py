from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.local_workspace_registry import LocalWorkspaceRegistry


class LocalWorkspaceRegistryTests(unittest.TestCase):
    def test_workspace_path_has_one_explicit_local_owner_and_optional_cloud_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = LocalWorkspaceRegistry(root / "profiles.sqlite3")
            profile = registry.add("Research", root / "workspace")
            self.assertEqual(profile["cloudAccountId"], "")
            bound = registry.bind_cloud_account(profile["id"], "cloud-user", "https://omnilit.example")
            self.assertEqual(bound["cloudAccountId"], "cloud-user")
            with self.assertRaisesRegex(ValueError, "already belongs"):
                registry.add("Legacy duplicate", root / "workspace")
            self.assertEqual(len(LocalWorkspaceRegistry(root / "profiles.sqlite3").profiles()), 1)


if __name__ == "__main__":
    unittest.main()
