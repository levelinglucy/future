"""Offline, disposable regression tests for graph snapshot comparison."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "compare_spiral_gardens.py"


def node(ident, location, seeds=(), anchors=(), score=1):
    return dict(id=ident, location=location, matched_seeds=list(seeds),
                matched_anchors=list(anchors), score=score)


def edge(ident, src, dst, via="seed", strength=0.37, evidence=("x",)):
    return dict(id=ident, source_node=src, target_node=dst, via=via,
                strength=strength, evidence=list(evidence))


def graph(nodes=(), edges=()):
    return dict(schema="spiral_garden_graph_v1", nodes=list(nodes), threads=list(edges))


class SnapshotDiffTests(unittest.TestCase):
    def run_cli(self, old, new):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "old.json", Path(directory) / "new.json"
            for path, data in ((a, old), (b, new)):
                path.write_text(data if isinstance(data, str) else json.dumps(data),
                                encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPT), str(a), str(b)],
                                  capture_output=True, text=True, timeout=15)

    def test_equal_graphs_report_no_changes(self):
        g = graph([node("n1", "🌱.txt", ["hello"])])
        proc = self.run_cli(g, g)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        diff = json.loads(proc.stdout)
        self.assertEqual(diff["schema"], "spiral_garden_diff_v1")
        self.assertEqual(diff["counts"], {
            "nodes": {"added": 0, "removed": 0, "changed": 0},
            "threads": {"added": 0, "removed": 0, "changed": 0}})

    def test_added_removed_modified_nodes_and_threads(self):
        old = graph([node("a", "a.txt", ["x"]), node("b", "b.txt", ["x"], ["new"]),
                     node("z", "old.txt", ["z"])], [edge("t", "a", "b")])
        new = graph([node("A2", "a.txt", ["x"], ["new"], 4),
                     node("B2", "b.txt", ["x"], ["new"]), node("x", "new.txt", ["z"])],
                    [edge("q", "B2", "A2", "anchor", 0.57, ("new", "x"))])
        proc = self.run_cli(old, new)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        diff = json.loads(proc.stdout)
        self.assertEqual(diff["counts"]["nodes"], {"added": 1, "removed": 1, "changed": 1})
        self.assertEqual(diff["nodes"]["changed"][0]["location"], "a.txt")
        self.assertEqual(diff["threads"]["changed"][0]["locations"], ["a.txt", "b.txt"])
        self.assertEqual(diff["counts"]["threads"], {"added": 0, "removed": 0, "changed": 1})

    def test_reordered_nodes_reversed_edges_and_new_internal_ids_are_stable(self):
        old = graph([node("a", "a.txt", ["x"]), node("b", "b.txt", ["x"])],
                    [edge("t", "a", "b")])
        new = graph([node("bb", "b.txt", ["x"]), node("aa", "a.txt", ["x"])],
                    [edge("changed", "bb", "aa")])
        diff = json.loads(self.run_cli(old, new).stdout)
        self.assertEqual(sum(diff["counts"]["nodes"].values()), 0)
        self.assertEqual(sum(diff["counts"]["threads"].values()), 0)

    def test_added_and_removed_edges_are_distinguished(self):
        base = [node("a", "a", ["x"]), node("b", "b", ["x"]), node("c", "c", ["x"])]
        old = graph(base, [edge("one", "a", "b")])
        new = graph(base, [edge("two", "b", "c")])
        diff = json.loads(self.run_cli(old, new).stdout)
        self.assertEqual(diff["counts"]["threads"], {"added": 1, "removed": 1, "changed": 0})

    def test_bad_inputs_do_not_emit_partial_output(self):
        good = graph()
        bad = [
            '{"schema":"spiral_garden_graph_v1","nodes":[],"nodes":[],"threads":[]}',
            '{"schema":"spiral_garden_graph_v1","nodes":[],"threads":[],"bad":NaN}',
            graph([node("n", "x", score=float("inf"))]),
            graph([node("a", "x"), node("b", "x")]),
            graph([node("a", "x", ["duplicate", "duplicate"])]),
            graph([node("a", "x")], [edge("one", "a", "missing")]),
            graph([node("a", "x"), node("b", "y")],
                  [edge("one", "a", "b"), edge("two", "b", "a")]),
        ]
        for candidate in bad:
            with self.subTest(candidate=str(candidate)[:40]):
                proc = self.run_cli(good, candidate)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, "")

    def test_edge_evidence_must_be_justified_by_endpoint_motifs(self):
        valid = graph([
            node("a", "a.txt", ["x", "y"], ["🌱"]),
            node("b", "b.txt", ["y", "x"], ["🌱"]),
        ], [edge("t", "a", "b", "anchor", 0.69, ("🌱", "x", "y"))])
        result = self.run_cli(valid, valid)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["counts"]["threads"]["changed"], 0)

        cases = [
            edge("fake", "a", "b", "seed", 0.69, ("🌱", "x", "y")),  # wrong via
            edge("fake", "a", "b", "anchor", 0.81, ("🌱", "x", "y")), # invented strength
            edge("fake", "a", "b", "anchor", 0.69, ("🌱", "x")),      # missing shared seed
            edge("fake", "a", "b", "anchor", 0.69, ("🌱", "x", "other")), # invented motif
            edge("fake", "a", "b", "anchor", 0.69, ("x", "🌱", "y")),   # noncanonical order
        ]
        for thread in cases:
            with self.subTest(thread=thread):
                proc = self.run_cli(valid, graph(valid["nodes"], [thread]))
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, "")

        # A plausible-looking edge with no shared motif is not graph evidence.
        none = graph([node("a", "a.txt", ["x"]), node("b", "b.txt", ["y"])],
                     [edge("fake", "a", "b", "seed", 0.37, ("x",))])
        proc = self.run_cli(valid, none)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")

    def test_unknown_schema_and_malformed_json_rejected(self):
        for invalid in ('[]', '{"schema":', '{}'):
            proc = self.run_cli(invalid, graph())
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")


    def test_exclusive_output_publishes_once_and_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            older, newer, output = (root / "before.json", root / "after.json", root / "diff.json")
            older.write_text(json.dumps(graph([node("a", "a.txt", ["x"])])), encoding="utf-8")
            newer.write_text(json.dumps(graph([node("b", "b.txt", ["x"])])), encoding="utf-8")
            command = [sys.executable, str(SCRIPT), str(older), str(newer), "--out", str(output)]
            first = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, "")
            diff = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(diff["counts"]["nodes"], {"added": 1, "removed": 1, "changed": 0})
            saved = output.read_bytes()
            second = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(second.stdout, "")
            self.assertEqual(output.read_bytes(), saved)
            self.assertEqual(sorted(p.name for p in root.iterdir()),
                             ["after.json", "before.json", "diff.json"])

    def test_exclusive_output_never_publishes_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            older, newer, output = root / "before.json", root / "after.json", root / "diff.json"
            older.write_text(json.dumps(graph()), encoding="utf-8")
            newer.write_text('{"schema":"spiral_garden_graph_v1","nodes":', encoding="utf-8")
            failed = subprocess.run([sys.executable, str(SCRIPT), str(older), str(newer),
                                     "--out", str(output)], capture_output=True, text=True, timeout=15)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(failed.stdout, "")
            self.assertFalse(output.exists())
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["after.json", "before.json"])

    def test_exclusive_output_publication_failure_cleans_staging(self):
        import compare_spiral_gardens as comparator
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "diff.json"
            report = comparator.compare(({}, {}), ({}, {}))
            with mock.patch.object(comparator.os, "link", side_effect=OSError("unsupported")):
                with self.assertRaises(OSError):
                    comparator.write_diff_exclusive(output, report)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.iterdir()), [])

if __name__ == "__main__":
    unittest.main()
