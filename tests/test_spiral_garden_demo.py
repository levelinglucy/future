"""Demonstrate the builder -> saved snapshots -> strict comparator workflow."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "spiral_garden_demo.py"


class EndToEndDemoTests(unittest.TestCase):
    def test_demo_uses_actual_saved_graphs_and_reports_expected_changes(self):
        # Run as a user would, from another working directory. The demo
        # creates only disposable synthetic notes and removes its own outputs.
        with tempfile.TemporaryDirectory() as location:
            process = subprocess.run(
                [sys.executable, str(DEMO)], cwd=location,
                text=True, capture_output=True, timeout=20,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("Nodes: +1 added, -1 removed, ~1 changed", process.stdout)
            self.assertIn("Threads: +2 added, -0 removed, ~1 changed", process.stdout)
            self.assertIn('"meadow.md"', process.stdout)
            self.assertIn('"retired.txt"', process.stdout)
            self.assertIn('"route.txt"', process.stdout)
            self.assertEqual(list(Path(location).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
