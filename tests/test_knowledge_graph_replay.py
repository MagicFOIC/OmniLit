from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_replay import build_replay_events


class KnowledgeGraphReplayTests(unittest.TestCase):
    def test_groups_sentence_nodes_and_edges_in_reading_order(self) -> None:
        first = {"page": 0, "bbox": [20, 80, 300, 110], "element_id": "b2", "excerpt": "We use Model A and achieve 91% accuracy."}
        earlier = {"page": 0, "bbox": [20, 20, 300, 50], "element_id": "b1", "excerpt": "We propose Model A."}
        graph = {
            "nodes": [
                {"id": "paper:p", "type": "paper", "evidence": []},
                {"id": "method:a", "type": "method", "evidence": [first]},
                {"id": "result:a", "type": "result", "evidence": [first]},
                {"id": "contribution:a", "type": "contribution", "evidence": [earlier]},
            ],
            "edges": [
                {"id": "e1", "source": "method:a", "target": "result:a", "type": "ACHIEVES", "relation_evidence": [first]},
                {"id": "e2", "source": "paper:p", "target": "contribution:a", "type": "PROPOSES", "relation_evidence": [earlier]},
            ],
        }
        events = build_replay_events(graph)
        self.assertEqual([item["elementId"] for item in events], ["b1", "b2"])
        self.assertEqual(events[1]["nodeCount"], 2)
        self.assertEqual(events[1]["edgeIds"], ["e1"])
        self.assertTrue(events[1]["relationCues"])

    def test_relation_only_evidence_creates_event_and_reveals_endpoints(self) -> None:
        evidence = {"page": "2", "bbox": [10, 30, 200, 55], "excerpt": "Model A uses Dataset B."}
        graph = {
            "nodes": [
                {"id": "method:a", "type": "method", "evidence": []},
                {"id": "dataset:b", "type": "dataset", "evidence": []},
            ],
            "edges": [
                {"id": "e1", "source": "method:a", "target": "dataset:b", "type": "USES", "relation_evidence": [evidence]},
            ],
        }

        events = build_replay_events(graph)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["page"], 2)
        self.assertEqual(events[0]["nodeIds"], ["method:a", "dataset:b"])
        self.assertEqual(events[0]["edgeIds"], ["e1"])

    def test_malformed_evidence_coordinates_do_not_abort_replay(self) -> None:
        graph = {
            "nodes": [{
                "id": "method:a", "type": "method",
                "evidence": [{"page": "unknown", "bbox": ["left", "top", 3, 4], "excerpt": "We use A."}],
            }],
            "edges": [],
        }

        events = build_replay_events(graph)

        self.assertEqual(events[0]["page"], -1)
        self.assertEqual(events[0]["nodeIds"], ["method:a"])


if __name__ == "__main__":
    unittest.main()
