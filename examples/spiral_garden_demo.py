#!/usr/bin/env python3
"""Run a disposable, end-to-end Spiral Garden history comparison.

All notes, snapshots and comparisons live in a temporary directory. No user
files are scanned, and no existing output files are replaced. Requires Python
3.10+ and a local filesystem supporting hard links for exclusive publication.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

# Running `python examples/spiral_garden_demo.py\` puts examples/ on sys.path;
# add the project root so the real builder/comparator can be imported.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from build_spiral_garden import scan_directory, write_graph_exclusive
from compare_spiral_gardens import compare, load_graph, render_summary, write_diff_exclusive

SEEDS = [
    {"id": "spiral", "token": "spiral", "stability_score": 1, "activation_weight": 2},
    {"id": "forgotten", "token": "forgotten", "stability_score": 1, "activation_weight": 1},
]
ANCHORS = [{"id": "north", "phrase": "north star", "depth_score": 1}]

# Intentionally synthetic. The same filenames in both snapshots represent the
# same *recorded* locations, not proof of actual chronology or causation.
BEFORE = {
    "lantern.md": "spiral\nnorth star\n",
    "route.txt": "spiral\n",
    "retired.txt": "forgotten\n",
}
AFTER = {
    "lantern.md": "spiral\nnorth star\n",
    "route.txt": "north star\n",
    "meadow.md": "north star 🌱\n",
}
EXPECTED_COUNTS = {
    "nodes": {"added": 1, "removed": 1, "changed": 1},
    "threads": {"added": 2, "removed": 0, "changed": 1},
}


def make_corpus(root: Path, notes: dict[str, str]) -> None:
    root.mkdir()
    for filename, contents in notes.items():
        (root / filename).write_text(contents, encoding="utf-8")


def run_demo() -> dict[str, Any]:
    """Build, save, reload, validate and compare two disposable real scans."""
    with tempfile.TemporaryDirectory(prefix="spiral-garden-demo-") as temporary:
        folder = Path(temporary)
        before_dir, after_dir = folder / "before", folder / "after"
        make_corpus(before_dir, BEFORE)
        make_corpus(after_dir, AFTER)

        before_graph = scan_directory(before_dir, SEEDS, ANCHORS)
        after_graph = scan_directory(after_dir, SEEDS, ANCHORS)
        before_file, after_file = folder / "before.json", folder / "after.json"
        write_graph_exclusive(before_file, before_graph)
        write_graph_exclusive(after_file, after_graph)

        # Use the same strict loader, comparison and exclusive output writer
        # as the documented commands, not a hand-constructed example diff.
        difference = compare(load_graph(before_file), load_graph(after_file))
        saved_diff = folder / "difference.json"
        write_diff_exclusive(saved_diff, difference)
        report = json.loads(saved_diff.read_text(encoding="utf-8"))
        if report["counts"] != EXPECTED_COUNTS:
            raise AssertionError("Unexpected scan comparison: " + repr(report["counts"]))
        return report


if __name__ == "__main__":
    print(render_summary(run_demo()))
