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

    def test_list_locations_is_sorted_bounded_and_reports_match_totals(self):
        listing = trace.list_locations(graph(), limit=2)
        self.assertIn("5 recorded matching-file locations", listing)
        self.assertIn('"a.md"', listing)
        self.assertIn('"b.md"', listing)
        self.assertNotIn('"c.md"', listing)
        self.assertIn("3 more", listing)
        filtered = trace.list_locations(graph(), contains="isolated")
        self.assertIn("1 of 5", filtered)
        self.assertIn('"isolated.md"', filtered)
        self.assertNotIn('"a.md"', filtered)
        self.assertIn("case-sensitive", filtered)
        empty = trace.list_locations(graph(), contains="NONEXISTENT")
        self.assertIn("0 of 5", empty)
        self.assertIn("No recorded paths match", empty)

    def test_list_locations_escapes_path_controls_and_rejects_bad_limit(self):
        unusual = "a" + chr(10) + "b.md"
        nodes = {unusual: {}, "plain.md": {}}
        listing = trace.list_locations((nodes, {}))
        self.assertIn(json.dumps(unusual), listing)
        self.assertNotIn(unusual, listing)
        with self.assertRaises(ValueError):
            trace.list_locations((nodes, {}), limit=0)

    def test_cli_lists_exact_locations_without_scanning_and_rejects_bad_modes(self):
        data = {"schema": "spiral_garden_graph_v1", "nodes": [
            {"id": f"n{i}", "location": location, "score": 1,
             "matched_seeds": [f"s{i}"], "matched_anchors": []}
            for i, location in enumerate(("notes/a.md", "notes/b.md", "z.md"))
        ], "threads": []}
        proc = self.run_cli(data, "--list", "--contains", "notes/", "--limit", "1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("2 of 3", proc.stdout)
        self.assertIn('"notes/a.md"', proc.stdout)
        self.assertNotIn('"notes/b.md"', proc.stdout)
        self.assertIn("1 more", proc.stdout)
        for args in (("--list", "--from", "z.md"),
                     ("--list", "--to", "z.md"),
                     ("--from", "z.md", "--contains", "notes/")):
            with self.subTest(args=args):
                bad = self.run_cli(data, *args)
                self.assertNotEqual(bad.returncode, 0)
                self.assertEqual(bad.stdout, "")
        malformed = '{"schema":"spiral_garden_graph_v1","nodes":[],"nodes":[],"threads":[]}'
        bad = self.run_cli(malformed, "--list")
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(bad.stdout, "")

    def test_list_exact_motif_ids_in_seeds_and_anchors(self):
        nodes = {
            "notes/one.md": {"matched_seeds": ["seed-1"], "matched_anchors": [], "score": 1},
            "notes/two.md": {"matched_seeds": ["seed-10"], "matched_anchors": [], "score": 1},
            "other.md": {"matched_seeds": [], "matched_anchors": ["anchor-1"], "score": 1},
            "notes/three.md": {"matched_seeds": [], "matched_anchors": ["anchor-1"], "score": 1},
        }
        data = (nodes, {})
        exact = trace.list_locations(data, motif="seed-1")
        self.assertIn('1 of 4', exact)
        self.assertIn('"notes/one.md"', exact)
        self.assertNotIn('"notes/two.md"', exact)
        self.assertIn('exact motif ID "seed-1"', exact)
        both = trace.list_locations(data, contains="notes/", motif="anchor-1")
        self.assertIn('1 of 4', both)
        self.assertIn('"notes/three.md"', both)
        self.assertNotIn('"other.md"', both)
        self.assertIn("case-sensitive", both)
        self.assertIn("exact motif ID", both)
        missing = trace.list_locations(data, motif="Seed-1")
        self.assertIn("0 of 4", missing)
        self.assertIn("No recorded paths match", missing)
        with self.assertRaises(ValueError):
            trace.list_locations(data, motif="")

    def test_cli_exact_motif_discovery_and_mode_errors(self):
        data = {"schema": "spiral_garden_graph_v1", "nodes": [
            {"id": "n1", "location": "notes/one.md", "score": 1,
             "matched_seeds": ["seed-1"], "matched_anchors": []},
            {"id": "n2", "location": "notes/two.md", "score": 1,
             "matched_seeds": ["seed-10"], "matched_anchors": []},
            {"id": "n3", "location": "other.md", "score": 1,
             "matched_seeds": [], "matched_anchors": ["anchor-1"]},
        ], "threads": []}
        selected = self.run_cli(data, "--list", "--motif", "seed-1")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertIn('"notes/one.md"', selected.stdout)
        self.assertNotIn('"notes/two.md"', selected.stdout)
        selected_anchor = self.run_cli(data, "--list", "--motif", "anchor-1")
        self.assertEqual(selected_anchor.returncode, 0, selected_anchor.stderr)
        self.assertIn('"other.md"', selected_anchor.stdout)
        for bad_args in (("--from", "notes/one.md", "--motif", "seed-1"),
                         ("--list", "--motif", "")):
            with self.subTest(bad_args=bad_args):
                bad = self.run_cli(data, *bad_args)
                self.assertNotEqual(bad.returncode, 0)
                self.assertEqual(bad.stdout, "")

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
