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


if __name__ == "__main__":
    unittest.main()
