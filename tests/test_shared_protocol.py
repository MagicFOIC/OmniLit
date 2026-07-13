from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from omnilit_qt.knowledge_graph_schema import KnowledgeGraphDocument, KnowledgeGraphEdge, KnowledgeGraphEvidence, KnowledgeGraphNode
from omnilit_qt.shared_protocol import SharedProtocolError, from_shared_graph_data, to_shared_graph_data, validate_collaboration_event_page, validate_collaboration_mutation_request, validate_collaboration_snapshot, validate_graph_data, validate_graph_timeline, validate_graph_timeline_query, validate_graph_view_save_request, validate_graph_view_state, validate_library_mutation_request, validate_library_state, validate_task


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "packages" / "shared-schema" / "fixtures" / "shared-graph-v1.json"
TIMELINE_FIXTURE = ROOT / "packages" / "shared-schema" / "fixtures" / "shared-timeline-v1.json"


class SharedProtocolTests(unittest.TestCase):
    def test_fixed_fixture_validates_and_tolerates_unknown_fields(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        validate_graph_data(payload)
        self.assertTrue(payload["futureCompatibleField"]["ignoredByV1Readers"])

    def test_python_document_round_trip_preserves_qml_compatibility(self) -> None:
        evidence = KnowledgeGraphEvidence(page=3, bbox=[1, 2, 3, 4], element_id="el-1", excerpt="evidence")
        document = KnowledgeGraphDocument(
            record_id="p1",
            paper={"title": "Paper", "year": "2025", "authors": [{"full_name": "Ada Example", "orcid": "0000"}]},
            nodes=[
                KnowledgeGraphNode("paper:p1", "paper", "Paper"),
                KnowledgeGraphNode("method:p1:1", "method", "Method", evidence=[evidence], details={"section": "Methods"}),
            ],
            edges=[KnowledgeGraphEdge("e1", "paper:p1", "method:p1:1", "USES_METHOD", evidence=[evidence])],
        )
        shared = to_shared_graph_data(document)
        self.assertTrue(shared["edges"][0]["directed"])
        self.assertEqual(shared["paper"]["year"], 2025)
        self.assertEqual(shared["paper"]["authors"][0]["name"], "Ada Example")
        restored = from_shared_graph_data(shared)
        legacy = restored.to_dict()
        self.assertEqual(legacy["recordId"], "p1")
        self.assertEqual(legacy["nodes"][1]["details"]["section"], "Methods")
        self.assertEqual(legacy["nodes"][1]["evidence"][0]["element_id"], "el-1")
        self.assertEqual(legacy["edges"][0]["type"], "USES_METHOD")

    def test_incompatible_versions_have_explicit_errors(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["protocolVersion"] = "2.0"
        with self.assertRaisesRegex(SharedProtocolError, "expected major version 1") as context:
            validate_graph_data(payload)
        self.assertEqual(context.exception.code, "unsupported_protocol_version")

    def test_generated_types_are_in_sync_with_authoritative_schema(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/codegen/generate_shared_schema_types.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_task_contract_supports_progress_result_reference_and_succeeded_status(self) -> None:
        validate_task({
            "protocolVersion": "1.0", "id": "task-1", "type": "graph.audit", "status": "succeeded", "cancellable": False,
            "progress": {"completed": 2, "total": 2, "unit": "records", "message": "Succeeded"},
            "message": "Succeeded", "createdAt": "2026-07-13T00:00:00Z", "startedAt": "2026-07-13T00:00:01Z",
            "finishedAt": "2026-07-13T00:00:02Z", "resultRef": "/v1/tasks/task-1/result"
        })
        with self.assertRaises(SharedProtocolError):
            validate_task({"protocolVersion": "1.0", "id": "task-2", "type": "graph.audit", "status": "unknown", "cancellable": True, "progress": {"completed": 0, "total": 1, "unit": "task"}})

    def test_collaboration_contract_bounds_mutations_snapshots_and_recovery_pages(self) -> None:
        mutation = {"protocolVersion": "1.0", "baseRevision": 0, "clientMutationId": "11111111-1111-4111-8111-111111111111", "action": "upsert", "targetType": "node", "targetId": "paper:paper-001", "body": "Review"}
        validate_collaboration_mutation_request(mutation)
        validate_collaboration_snapshot({"protocolVersion": "1.0", "recordId": "paper-001", "revision": 0, "canEdit": True, "syncEnabled": True, "annotations": []})
        validate_collaboration_event_page({"protocolVersion": "1.0", "recordId": "paper-001", "afterRevision": 0, "currentRevision": 0, "events": [], "hasMore": False, "resetRequired": False})
        with self.assertRaises(SharedProtocolError):
            validate_collaboration_mutation_request({**mutation, "body": "x" * 4001})

    def test_saved_view_contract_is_typed_and_bounded(self) -> None:
        request = {
            "protocolVersion": "1.0", "name": "Authors", "exploration": {"nodeIds": [], "edgeIds": [], "pages": {}},
            "filters": {"mode": "all", "searchText": "Ada", "density": "normal", "literatureSortKey": "relevance", "literatureSortDescending": True, "facets": {}, "nodeTypes": ["author"], "needsReviewOnly": False},
            "selection": {"nodeId": "", "edgeId": ""},
            "viewport": {"displayStyle": "academic", "focusDepth": 0, "reviewMode": False, "graphScale": 1, "panX": 0, "panY": 0, "showArrows": True, "showLabels": True, "dimUnrelated": True, "textFadeThreshold": 1.15, "nodeSizeScale": 1, "linkThickness": 1, "animateLayout": False},
        }
        validate_graph_view_save_request(request)
        state = {**request, "version": 2, "id": "view-1", "recordId": "paper-001", "createdAt": "2026-07-13T00:00:00Z", "updatedAt": "2026-07-13T00:00:00Z", "graphFingerprint": "fixture", "path": {"startId": "", "endId": "", "directed": False, "relationFilter": "ALL"}}
        validate_graph_view_state(state)
        with self.assertRaises(SharedProtocolError):
            validate_graph_view_save_request({**request, "name": ""})

    def test_timeline_fixture_and_query_share_one_bounded_contract(self) -> None:
        timeline = json.loads(TIMELINE_FIXTURE.read_text(encoding="utf-8"))
        validate_graph_timeline(timeline)
        validate_graph_timeline_query({"protocolVersion": "1.0", "startYear": 2020, "endYear": 2024, "playbackYear": 2022, "viewport": {"width": 1280, "height": 720, "scale": 1}})
        self.assertEqual(timeline["events"][-1]["papers"][0]["nodeId"], "paper:timeline-2024")
        with self.assertRaises(SharedProtocolError):
            validate_graph_timeline_query({"protocolVersion": "1.0", "viewport": {"width": 0, "height": 720, "scale": 1}})

    def test_library_state_requires_revision_and_bounded_workspace(self) -> None:
        state = {"protocolVersion": "1.0", "revision": 2, "updatedAt": "", "syncState": "local_only", "collections": [{"id": "core", "name": "核心文献", "builtIn": True, "recordCount": 1}], "favorites": {"paper-1": ["core"]}, "workspace": {"compareRecordIds": ["paper-1"]}}
        validate_library_state(state)
        validate_library_mutation_request({"protocolVersion": "1.0", "action": "toggle_compare_record", "expectedRevision": 2, "recordId": "paper-2"})
        with self.assertRaises(SharedProtocolError):
            validate_library_mutation_request({"protocolVersion": "1.0", "action": "clear_compare"})
        with self.assertRaises(SharedProtocolError):
            validate_library_state({**state, "workspace": {"compareRecordIds": ["1", "2", "3", "4", "5"]}})


if __name__ == "__main__":
    unittest.main()
