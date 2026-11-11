#!/usr/bin/env python3
"""Compare saved Spiral Garden v1 graphs without changing either input.

Structural evidence comparison, not chronological or causal verification.
See docs/SPIRAL_GARDEN.md for intended usage and limits.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def reject_constant(token):
    raise ValueError(f"nonstandard JSON number: {token}")


def valid_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field} must be valid UTF-8") from exc
    return value


def valid_ids(value, field):
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    values = [valid_string(item, field) for item in value]
    if len(set(values)) != len(values):
        raise ValueError(f"{field} contains duplicate identifiers")
    return values


def finite_number(value, field):
    if type(value) not in (float, int):
        raise ValueError(f"{field} must be a finite number")
    try:
        finite = math.isfinite(value)
    except (ValueError, OverflowError):
        finite = False
    if not finite:
        raise ValueError(f"{field} must be a finite number")
    return value


def load_graph(path: Path):
    """Refuse malformed or ambiguous fields before any comparison is emitted."""
    try:
        with path.open("r", encoding="utf-8") as f:
            graph = json.load(f, object_pairs_hook=unique_object,
                              parse_constant=reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(graph, dict) or graph.get("schema") != "spiral_garden_graph_v1":
        raise ValueError(f"{path} is not a spiral_garden_graph_v1 graph")
    if not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("threads"), list):
        raise ValueError("graph nodes and threads must be arrays")

    nodes = {}
    id_locations = {}
    for index, node in enumerate(graph["nodes"], 1):
        if not isinstance(node, dict):
            raise ValueError(f"node {index} must be an object")
        ident = valid_string(node.get("id"), f"node {index} id")
        location = valid_string(node.get("location"), f"node {index} location")
        if ident in id_locations or location in nodes:
            raise ValueError(f"duplicate node ID or location at node {index}")
        id_locations[ident] = location
        nodes[location] = {
            "matched_seeds": valid_ids(node.get("matched_seeds"), f"node {index} matched_seeds"),
            "matched_anchors": valid_ids(node.get("matched_anchors"), f"node {index} matched_anchors"),
            "score": finite_number(node.get("score"), f"node {index} score"),
        }

    threads = {}
    thread_ids = set()
    for index, thread in enumerate(graph["threads"], 1):
        if not isinstance(thread, dict):
            raise ValueError(f"thread {index} must be an object")
        ident = valid_string(thread.get("id"), f"thread {index} id")
        source = valid_string(thread.get("source_node"), f"thread {index} source")
        target = valid_string(thread.get("target_node"), f"thread {index} target")
        if ident in thread_ids:
            raise ValueError(f"duplicate thread ID {ident!r}")
        if source not in id_locations or target not in id_locations or source == target:
            raise ValueError(f"thread {index} has missing or identical endpoints")
        pair = tuple(sorted((id_locations[source], id_locations[target])))
        if pair in threads:
            raise ValueError(f"duplicate thread endpoints {pair!r}")
        # A graph edge is derived entirely from motifs present at *both*
        # endpoints. Otherwise malformed or invented evidence could enter a
        # convincing-looking saved comparison without any actual shared match.
        a, b = nodes[id_locations[source]], nodes[id_locations[target]]
        shared_seeds = sorted(set(a["matched_seeds"]) & set(b["matched_seeds"]))
        shared_anchors = sorted(set(a["matched_anchors"]) & set(b["matched_anchors"]))
        expected_evidence = shared_anchors + shared_seeds
        if not expected_evidence:
            raise ValueError(f"thread {index} has no shared endpoint motifs")
        via = thread.get("via")
        expected_via = "anchor" if shared_anchors else "seed"
        if via != expected_via:
            raise ValueError(f"thread {index} via disagrees with shared motifs")
        evidence = valid_ids(thread.get("evidence"), f"thread {index} evidence")
        if evidence != expected_evidence:
            raise ValueError(f"thread {index} evidence disagrees with shared motifs")
        strength = finite_number(thread.get("strength"), f"thread {index} strength")
        expected_strength = round(min(
            1.0, 0.25 + 0.12 * len(shared_seeds) + 0.2 * len(shared_anchors)
        ), 3)
        if strength != expected_strength:
            raise ValueError(f"thread {index} strength disagrees with shared motifs")
        threads[pair] = {
            "via": via,
            "strength": strength,
            "evidence": evidence,
        }
        thread_ids.add(ident)
    return nodes, threads


def diff_table(before, after, field):
    previous, current = set(before), set(after)
    return {
        "added": [{field: key, "value": after[key]} for key in sorted(current - previous)],
        "removed": [{field: key, "value": before[key]} for key in sorted(previous - current)],
        "changed": [{field: key, "before": before[key], "after": after[key]}
                    for key in sorted(previous & current) if before[key] != after[key]],
    }


def compare(before, after):
    nodes = diff_table(before[0], after[0], "location")
    threads = diff_table(before[1], after[1], "locations")
    for group in ("added", "removed", "changed"):
        for item in threads[group]:
            item["locations"] = list(item["locations"])
    return {
        "schema": "spiral_garden_diff_v1",
        "nodes": nodes,
        "threads": threads,
        "counts": {
            "nodes": {group: len(nodes[group]) for group in ("added", "removed", "changed")},
            "threads": {group: len(threads[group]) for group in ("added", "removed", "changed")},
        },
    }



def write_diff_exclusive(out_path: Path, report: dict[str, Any]) -> None:
    """Save a complete comparison only under a previously absent filename.

    A private same-directory staging file is fsynced, then published using
    exclusive hard-link creation. Do not fall back to a partial destination
    copy if linking is unsupported. This is not crash/power-loss certification.
    """
    if out_path.exists() or out_path.is_symlink():
        raise FileExistsError(f"output already exists: {out_path}")

    fd, staged_name = tempfile.mkstemp(
        prefix=".spiral-diff-", suffix=".tmp", dir=out_path.parent
    )
    staged = Path(staged_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        # The final path is created only if absent, including symlink paths.
        os.link(staged, out_path)
    finally:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="Earlier saved Spiral Garden graph")
    parser.add_argument("after", type=Path, help="Later saved Spiral Garden graph")
    parser.add_argument("--out", type=Path,
                        help="Exclusively save a complete JSON diff to a new path")
    args = parser.parse_args()
    try:
        result = compare(load_graph(args.before), load_graph(args.after))
        if args.out is not None:
            write_diff_exclusive(args.out, result)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    except FileExistsError:
        parser.error("--out already exists; choose a new comparison filename")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
