from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from omnilit_qt.research_business_shared import (
    BusinessSettingsConflict,
    BusinessSettingsStore,
    build_research_brief,
    project_research_statistics,
    project_research_workspace,
)


class _Context:
    def __init__(self) -> None:
        self.progress: list[tuple[float, float, str, str]] = []

    def check_cancelled(self) -> None:
        return None

    def report(self, completed: float, total: float, unit: str, message: str = "") -> None:
        self.progress.append((completed, total, unit, message))


def _state() -> dict:
    return {
        "revision": 2,
        "updated_at": "",
        "projects": [{"id": "core", "name": "Core", "built_in": True}],
        "favorites": {"paper-1": ["core"]},
        "compare": {"active": ["paper-1"]},
    }


def _records() -> list[dict]:
    return [{
        "recordId": "paper-1", "title": "Evidence Systems", "authorsText": "Ada", "year": "2025",
        "source": "Crossref", "journalTitle": "Open Research", "abstract": "A bounded evidence workflow.",
        "keywordsText": "evidence; workflow", "pdfStatus": "downloaded", "localPdfPath": "private/paper.pdf",
        "hasExtraction": True,
    }]


def _update(revision: int, **overrides) -> dict:
    payload = {
        "protocolVersion": "1.0", "expectedRevision": revision, "themeMode": "system",
        "density": "comfortable", "reduceMotion": False, "highContrast": False,
        "startPage": "graph", "defaultLibrarySort": "relevance_desc", "aiEvidenceLimit": 4,
        "aiEndpoint": "", "aiModel": "", "allowRemoteResearchContent": False,
    }
    payload.update(overrides)
    return payload


class ResearchBusinessSharedTests(unittest.TestCase):
    def test_workspace_and_statistics_project_shared_state_without_local_paths(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = project_research_workspace(Path(directory), True, _records(), _state())
        self.assertEqual(workspace["status"], "ready")
        self.assertEqual(workspace["records"][0]["collectionIds"], ["core"])
        self.assertNotIn("localPdfPath", workspace["records"][0])
        statistics = project_research_statistics(True, _records(), _state())
        self.assertEqual(statistics["totalRecords"], 1)
        self.assertEqual(statistics["downloadedRecords"], 1)
        self.assertEqual(statistics["extractedRecords"], 1)
        self.assertEqual(statistics["topKeywords"][0]["count"], 1)

    def test_settings_are_revisioned_recover_corruption_and_never_persist_credentials(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"OMNILIT_AI_API_KEY": "environment-secret"}):
            path = Path(directory) / "settings.json"
            store = BusinessSettingsStore(path)
            initial = store.load()
            self.assertTrue(initial["aiCredentialConfigured"])
            updated = store.update(_update(0, startPage="workspace", aiEndpoint="https://provider.example/v1/chat", aiModel="bounded-model", allowRemoteResearchContent=True))
            self.assertEqual(updated["revision"], 1)
            self.assertEqual(updated["startPage"], "workspace")
            self.assertNotIn("environment-secret", path.read_text(encoding="utf-8"))
            with self.assertRaises(BusinessSettingsConflict):
                store.update(_update(0))
            with self.assertRaises(ValueError):
                store.update(_update(1, aiEndpoint="http://insecure.example", aiModel="model"))
            path.write_text("{broken", encoding="utf-8")
            recovered = store.load()
            self.assertEqual(recovered["revision"], 0)
            self.assertTrue(list(Path(directory).glob("settings.json.*.bak")))

    def test_local_brief_is_evidence_labeled_and_remote_mode_requires_explicit_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = project_research_workspace(Path(directory), True, _records(), _state())
        context = _Context()
        request = {"protocolVersion": "1.0", "recordIds": ["paper-1"], "focus": "overview", "question": "What is bounded?", "mode": "evidence_only"}
        local = build_research_brief(workspace, request, context, {})
        self.assertEqual(local["mode"], "evidence_only")
        self.assertIn("未调用生成式模型", local["warnings"][0])
        self.assertEqual(context.progress[-1][0], 3)

        captured: list[str] = []
        settings = {"allowRemoteResearchContent": True, "aiEndpoint": "https://provider.example/v1/chat", "aiModel": "bounded-model"}
        remote = build_research_brief(workspace, {**request, "mode": "model"}, _Context(), settings, completion=lambda _settings, prompt: captured.append(prompt) or "Synthesis")
        self.assertEqual(remote["mode"], "model")
        self.assertEqual(remote["sections"][0]["body"], "Synthesis")
        self.assertIn("Evidence Systems", captured[0])


if __name__ == "__main__":
    unittest.main()
