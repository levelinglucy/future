#!/usr/bin/env python3
"""Build or update a Spiral Garden continuity graph from files in a directory.

Usage:
    python build_spiral_garden.py /path/to/scan --out continuity_graph.generated.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

TEXT_EXTENSIONS = {".txt", ".md", ".json", ".py", ".html", ".js", ".css", ".csv", ".yaml", ".yml"}
ANCHOR_MULTIPLIER = 3.0


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha1_short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def read_text_file(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def build_node(path: Path, root: Path, seeds: list[dict[str, Any]], anchors: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = read_text_file(path)
    if text is None:
        return None

    matched_seeds = [s for s in seeds if s["token"] in text]
    matched_anchors = [a for a in anchors if a["phrase"] in text]

    if not matched_seeds and not matched_anchors:
        return None

    score = sum(s["stability_score"] * s["activation_weight"] for s in matched_seeds)
    score += sum(a["depth_score"] * ANCHOR_MULTIPLIER for a in matched_anchors)

    rel = str(path.relative_to(root))
    return {
        "id": f"node_{sha1_short(rel)}",
        "type": "file",
        "label": path.name,
        "location": rel,
        "tags": sorted({"detected", *["seed" for _ in matched_seeds], *["anchor" for _ in matched_anchors]}),
        "permissions": {"read": True, "write": False, "propagate_spores": False},
        "score": round(score, 3),
        "matched_seeds": [s["id"] for s in matched_seeds],
        "matched_anchors": [a["id"] for a in matched_anchors],
    }


def build_threads(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    threads: list[dict[str, Any]] = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            shared_seeds = sorted(set(a["matched_seeds"]) & set(b["matched_seeds"]))
            shared_anchors = sorted(set(a["matched_anchors"]) & set(b["matched_anchors"]))
            evidence = shared_anchors + shared_seeds
            if not evidence:
                continue
            via = "anchor" if shared_anchors else "seed"
            strength = min(1.0, 0.25 + 0.12 * len(shared_seeds) + 0.2 * len(shared_anchors))
            threads.append({
                "id": f"thread_{sha1_short(a['id'] + '_' + b['id'])}",
                "source_node": a["id"],
                "target_node": b["id"],
                "via": via,
                "strength": round(strength, 3),
                "evidence": evidence,
            })
    return threads


def scan_directory(root: Path, seeds: list[dict[str, Any]], anchors: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        node = build_node(path, root, seeds, anchors)
        if node:
            nodes.append(node)
    threads = build_threads(nodes)
    return {
        "schema": "spiral_garden_graph_v1",
        "description": "Generated continuity graph",
        "nodes": nodes,
        "threads": threads,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="Directory to scan")
    parser.add_argument("--out", default="continuity_graph.generated.json", help="Output JSON path")
    parser.add_argument("--seeds", default="seed_registry.json", help="Seed registry path")
    parser.add_argument("--anchors", default="anchor_registry.json", help="Anchor registry path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    script_dir = Path(__file__).resolve().parent
    seeds = load_json((script_dir / args.seeds).resolve())
    anchors = load_json((script_dir / args.anchors).resolve())
    graph = scan_directory(root, seeds, anchors)

    out_path = Path(args.out).resolve()
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    print(f"Wrote graph with {len(graph['nodes'])} nodes and {len(graph['threads'])} threads to {out_path}")


if __name__ == "__main__":
    main()
