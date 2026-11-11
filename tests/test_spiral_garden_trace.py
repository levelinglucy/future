"""Disposable, offline tests for read-only Spiral Garden graph exploration."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "trace_spiral_garden.py"
spec = importlib.util.spec_from_file_location("trace_spiral_garden", SCRIPT)
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


def graph():
    nodes = {name: {"matched_seeds": [], "matched_anchors": [], "score": 1}
             for name in ("a.md", "b.md", "c.md", "d.md", "isolated.md")}
    edge = {"via": "seed", "strength": 0.37, "evidence": ["x"]}
    # Two equal-hop routes from a to d; lexical choice goes through b.
    threads = {("a.md", "c.md"): edge, ("a.md", "b.md"): edge,
               ("b.md", "d.md"): edge, ("c.md", "d.md"): edge}
    return nodes, threads


class TraceTests(unittest.TestCase):
    def test_shortest_route_is_deterministic_and_undirected(self):
        adj = trace.adjacency_for(*graph())
        self.assertEqual(trace.shortest_path(adj, "a.md", "d.md"),
                         ["a.md", "b.md", "d.md"])
        self.assertEqual(trace.shortest_path(adj, "d.md", "a.md"),
                         ["d.md", "b.md", "a.md"])

    def test_no_route_and_zero_hop_are_explicit(self):
        self.assertIn("No recorded path", trace.describe(graph(), "a.md", "isolated.md"))
        self.assertIn("0 connection(s)", trace.describe(graph(), "a.md", "a.md"))

    def test_neighbors_sorted_bounded_and_counted(self):
        summary = trace.describe(graph(), "a.md", limit=1)
        self.assertIn('neighbors of "a.md": 2', summary)
        self.assertIn('"b.md"', summary)
        self.assertNotIn('"c.md"', summary)
        self.assertIn("1 more", summary)

    def test_missing_location_and_bad_limit_are_errors(self):
        for kwargs in ({"origin": "not found"}, {"origin": "a.md", "target": "missing"},
                       {"origin": "a.md", "limit": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                trace.describe(graph(), **kwargs)

    def test_paths_and_motif_control_characters_are_escaped(self):
        weird = 'first\nsecond.md'
        nodes = {weird: {}, "next.md": {}}
        threads = {(weird, "next.md"): {"via": "seed", "strength": 0.37,
                                         "evidence": ["line\nbreak"]}}
        rendered = trace.describe((nodes, threads), weird)
        self.assertIn('"first\\nsecond.md"', rendered)
        self.assertIn('"line\\nbreak"', rendered)
        self.assertNotIn("first\nsecond", rendered)

    def run_cli(self, raw, *args):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(raw if isinstance(raw, str) else json.dumps(raw), encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPT), str(path), *args],
                                  capture_output=True, text=True, timeout=15)

    def test_cli_real_v1_graph_and_no_path(self):
        data = {"schema": "spiral_garden_graph_v1", "nodes": [
            {"id": "n1", "location": "a.md", "score": 1,
             "matched_seeds": ["x"], "matched_anchors": []},
            {"id": "n2", "location": "b.md", "score": 1,
             "matched_seeds": ["x", "y"], "matched_anchors": []},
            {"id": "n3", "location": "c.md", "score": 1,
             "matched_seeds": ["y"], "matched_anchors": []},
            {"id": "n4", "location": "solo.md", "score": 1,
             "matched_seeds": ["z"], "matched_anchors": []}],
            "threads": [
                {"id": "e1", "source_node": "n1", "target_node": "n2", "via": "seed",
                 "evidence": ["x"], "strength": 0.37},
                {"id": "e2", "source_node": "n2", "target_node": "n3", "via": "seed",
                 "evidence": ["y"], "strength": 0.37}]}
        proc = self.run_cli(data, "--from", "a.md", "--to", "c.md")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("2 connection(s)", proc.stdout)
        self.assertIn('"a.md" <-> "b.md"', proc.stdout)
        proc2 = self.run_cli(data, "--from", "a.md", "--to", "solo.md")
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        self.assertIn("No recorded path", proc2.stdout)

    def test_cli_rejects_contradictory_graph_without_partial_stdout(self):
        malformed = '{"schema":"spiral_garden_graph_v1","nodes":[],"nodes":[],"threads":[]}'
        proc = self.run_cli(malformed, "--from", "anything")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
