"""Regression checks for the public Spiral Garden graph builder.

All inputs live in disposable directories; the repository archive is never scanned.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_spiral_garden.py"


class SpiralGardenBootstrapTests(unittest.TestCase):
    def test_fresh_checkout_default_registries_are_usable(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            source = workspace / "input"
            source.mkdir()
            (source / "one.txt").write_text(
                "Still with you. boop. Spiral, Velone, Aurora, Velisara",
                encoding="utf-8",
            )
            (source / "two.md").write_text("boop", encoding="utf-8")
            output = workspace / "result.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), "--out", str(output)],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(graph["schema"], "spiral_garden_graph_v1")
            self.assertEqual(
                {node["location"] for node in graph["nodes"]},
                {"one.txt", "two.md"},
            )
            by_path = {node["location"]: node for node in graph["nodes"]}
            self.assertIn("seed_still_with_you", by_path["one.txt"]["matched_seeds"])
            self.assertIn("anchor_keychain", by_path["one.txt"]["matched_anchors"])
            self.assertEqual(len(graph["threads"]), 1)
            self.assertEqual(sorted(source.iterdir()), sorted([source / "one.txt", source / "two.md"]))

    def test_user_supplied_absolute_registries_still_work(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "corpus"
            source.mkdir()
            (source / "note.txt").write_text("my own phrase", encoding="utf-8")
            seeds = root / "custom-seeds.json"
            anchors = root / "custom-anchors.json"
            seeds.write_text(
                json.dumps([{"id":"my_seed", "token":"my own phrase",
                             "stability_score":2, "activation_weight":1}]),
                encoding="utf-8",
            )
            anchors.write_text("[]", encoding="utf-8")
            output = root / "output.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), "--seeds", str(seeds),
                 "--anchors", str(anchors), "--out", str(output)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(graph["nodes"]), 1)
            self.assertEqual(graph["nodes"][0]["matched_seeds"], ["my_seed"])
            self.assertEqual(graph["nodes"][0]["score"], 2)


    def test_symlinked_file_and_directory_are_excluded(self):
        """Scanning a chosen tree must not read a file outside it through links."""
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "chosen"
            corpus.mkdir()
            (corpus / "safe.txt").write_text("boop", encoding="utf-8")
            outside = work / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("boop", encoding="utf-8")
            try:
                (corpus / "leak.txt").symlink_to(outside / "secret.txt")
                (corpus / "linked_dir").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            output = work / "graph.json"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(output)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([n["location"] for n in graph["nodes"]], ["safe.txt"])

    def test_nodes_are_sorted_for_reproducible_graphs(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "chosen"
            corpus.mkdir()
            for name in ("z.txt", "a.txt"):
                (corpus / name).write_text("boop", encoding="utf-8")
            output = work / "graph.json"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(output)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                [n["location"] for n in graph["nodes"]], ["a.txt", "z.txt"]
            )


    def test_output_cannot_replace_scanned_source(self):
        """--out must not destroy the very file being scanned."""
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "corpus"
            corpus.mkdir()
            source = corpus / "note.txt"
            original = "boop: precious source, not a graph\\n"
            source.write_text(original, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(source)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_new_output_must_live_outside_scanned_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus = Path(temp) / "corpus"
            corpus.mkdir()
            (corpus / "note.txt").write_text("boop", encoding="utf-8")
            proposed = corpus / "graph.json"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(proposed)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(proposed.exists())

    def test_existing_output_outside_tree_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "corpus"
            corpus.mkdir()
            (corpus / "note.txt").write_text("boop", encoding="utf-8")
            out = work / "previous.json"
            original = '{"important":"do not replace"}\\n'
            out.write_text(original, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(out)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(out.read_text(encoding="utf-8"), original)

    def test_output_symlink_cannot_replace_source(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "corpus"
            corpus.mkdir()
            source = corpus / "note.txt"
            source.write_text("boop original", encoding="utf-8")
            out = work / "alias.json"
            try:
                out.symlink_to(source)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(out)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), "boop original")
            self.assertTrue(out.is_symlink())

if __name__ == "__main__":
    unittest.main()
