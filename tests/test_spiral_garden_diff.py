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
    def run_cli(self, old, new, *extra):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "old.json", Path(directory) / "new.json"
            for path, data in ((a, old), (b, new)):
                path.write_text(data if isinstance(data, str) else json.dumps(data),
                                encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPT), str(a), str(b), *extra],
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
        # Each snapshot must contain every edge implied by its own motifs.
        old = graph([node("a", "a", ["x"]), node("b", "b", ["x"]),
                     node("c", "c", ["z"])], [edge("one", "a", "b")])
        new = graph([node("a", "a", ["x"]), node("b", "b", ["y"]),
                     node("c", "c", ["y"])],
                    [edge("two", "b", "c", evidence=("y",))])
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

    def test_omitted_only_required_thread_is_rejected(self):
        # A snapshot with two files sharing x cannot honestly have no edge.
        nodes = [node("a", "a.txt", ["x"]), node("b", "b.txt", ["x"])]
        valid = graph(nodes, [edge("ab", "a", "b")])
        self.assertEqual(self.run_cli(valid, valid).returncode, 0)
        for before, after in ((graph(nodes), valid), (valid, graph(nodes))):
            with self.subTest(before=before == valid):
                proc = self.run_cli(before, after)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, "")

    def test_partial_edge_inventory_is_rejected(self):
        # An invented clean diff must not hide the missing b-c connection.
        nodes = [node("a", "a.txt", ["x"]), node("b", "b.txt", ["x", "y"]),
                 node("c", "c.txt", ["y"])]
        valid = graph(nodes, [
            edge("ab", "a", "b", evidence=("x",)),
            edge("bc", "b", "c", evidence=("y",)),
        ])
        partial = graph(nodes, [edge("ab", "a", "b", evidence=("x",))])
        result = self.run_cli(valid, partial)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_sparse_graph_without_shared_motifs_remains_valid(self):
        # Avoid requiring all-pairs edges for unrelated files.
        sparse = graph([node("n" + str(i), "f" + str(i) + ".txt",
                             ["different-" + str(i)])
                        for i in range(30)])
        result = self.run_cli(sparse, sparse)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["counts"]["threads"]["changed"], 0)

    def test_missing_thread_refuses_saved_comparison_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after, out = root / "before.json", root / "after.json", root / "diff.json"
            nodes = [node("a", "a.txt", ["x"]), node("b", "b.txt", ["x"])]
            before.write_text(json.dumps(graph(nodes, [edge("ab", "a", "b")])),
                              encoding="utf-8")
            after.write_text(json.dumps(graph(nodes)), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(before), str(after), "--out", str(out)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(out.exists())
            self.assertEqual(sorted(root.iterdir()), [after, before])

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


    def test_summary_readable_counts_and_paths_without_changing_json_default(self):
        older = graph([node("a", "a.txt", ["x"]), node("b", "b.txt", ["x"]),
                       node("old", "old.txt", ["z"])],
                      [edge("ab", "a", "b")])
        newer = graph([node("a2", "a.txt", ["x"], ["🌱"], 4),
                       node("b2", "b.txt", ["x"], ["🌱"], 4),
                       node("new", "new\nline.txt", ["z"])],
                      [edge("ab2", "a2", "b2", "anchor", 0.57, ("🌱", "x"))])
        report = self.run_cli(older, newer, "--summary")
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertIn("Nodes: +1 added, -1 removed, ~2 changed", report.stdout)
        self.assertIn("Threads: +0 added, -0 removed, ~1 changed", report.stdout)
        self.assertIn('  + "new\\nline.txt"', report.stdout)
        self.assertIn('  - "old.txt"', report.stdout)
        self.assertIn('  ~ "a.txt"', report.stdout)
        self.assertIn('  ~ "a.txt" <-> "b.txt"', report.stdout)
        self.assertNotIn("new\nline.txt", report.stdout)  # no forged terminal line
        default = self.run_cli(older, newer)
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(json.loads(default.stdout)["counts"]["nodes"]["changed"], 2)

    def test_summary_no_changes_and_bounded_preview(self):
        import compare_spiral_gardens as comparator
        unchanged = self.run_cli(graph(), graph(), "--summary")
        self.assertEqual(unchanged.returncode, 0, unchanged.stderr)
        self.assertIn("No recorded changes.", unchanged.stdout)
        later_nodes = {
            f"f{i}.txt": {"matched_seeds": ["x"], "matched_anchors": [], "score": 1}
            for i in range(5)
        }
        text = comparator.render_summary(
            comparator.compare(({}, {}), (later_nodes, {})), limit=2
        )
        self.assertIn("Nodes: +5 added", text)
        self.assertIn('  + "f0.txt"', text)
        self.assertIn('  + "f1.txt"', text)
        self.assertNotIn('  + "f2.txt"', text)
        self.assertIn("... 3 more", text)

    def test_summary_rejects_bad_input_and_incompatible_saved_mode(self):
        good, invalid = graph(), '{"schema":"spiral_garden_graph_v1","nodes":'
        bad = self.run_cli(good, invalid, "--summary")
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(bad.stdout, "")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after, output = root / "a.json", root / "b.json", root / "report.txt"
            before.write_text(json.dumps(good), encoding="utf-8")
            after.write_text(json.dumps(good), encoding="utf-8")
            rejected = subprocess.run(
                [sys.executable, str(SCRIPT), str(before), str(after), "--summary",
                 "--out", str(output)], capture_output=True, text=True, timeout=15
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")
            self.assertFalse(output.exists())

if __name__ == "__main__":
    unittest.main()
