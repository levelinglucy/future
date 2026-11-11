#!/usr/bin/env python3
"""Build or update a Spiral Garden continuity graph from files in a directory.

Usage:
    python build_spiral_garden.py /path/to/scan --out continuity_graph.generated.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

TEXT_EXTENSIONS = {".txt", ".md", ".json", ".py", ".html", ".js", ".css", ".csv", ".yaml", ".yml"}
ANCHOR_MULTIPLIER = 3.0


def load_json(path: Path) -> Any:
    """Read registry JSON without silently discarding duplicate keys."""

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate registry JSON key: {key!r}")
            result[key] = value
        return result

    def reject_constant(token):
        raise ValueError(f"nonstandard registry number: {token}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(
            f, object_pairs_hook=unique_object, parse_constant=reject_constant
        )


def finite_number(value: Any) -> bool:
    """Reject bool and numerically unrepresentable registry values."""
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (ValueError, OverflowError):
        return False


def validate_registry(entries: Any, kind: str) -> list[dict[str, Any]]:
    """Reject ambiguous or misleading motif definitions before scanning."""
    if not isinstance(entries, list):
        raise ValueError(f"{kind} registry must be a JSON array")
    term = "token" if kind == "seed" else "phrase"
    weights = ("stability_score", "activation_weight") if kind == "seed" else ("depth_score",)
    seen = set()
    for index, item in enumerate(entries, 1):
        label = f"{kind} registry entry {index}"
        if not isinstance(item, dict):
            raise ValueError(f"{label} must be an object")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError(f"{label} needs a nonempty string id")
        if identifier in seen:
            raise ValueError(f"{kind} registry has duplicate id: {identifier!r}")
        seen.add(identifier)
        phrase = item.get(term)
        if not isinstance(phrase, str) or not phrase.strip():
            raise ValueError(f"{label} needs a nonempty string {term}")
        # JSON permits escaped lone surrogates, but strict UTF-8 input files
        # cannot contain them. Refuse impossible motifs before scanning rather
        # than publishing a misleading empty match report.
        for field_name, text_value in (("id", identifier), (term, phrase)):
            try:
                text_value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError(
                    f"{label} {field_name} must be UTF-8 representable"
                ) from exc
        for name in weights:
            if not finite_number(item.get(name)):
                raise ValueError(f"{label} needs finite numeric {name}")
        contribution = (item["stability_score"] * item["activation_weight"]
                        if kind == "seed" else item["depth_score"] * ANCHOR_MULTIPLIER)
        if not finite_number(contribution):
            raise ValueError(f"{label} has an overflowing score contribution")
    return entries


def sha1_short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


TEXT_CHUNK_CHARS = 64 * 1024


def iter_text_chunks(path: Path):
    """Read strict UTF-8 in bounded chunks, preserving literal line endings.

    Continue decoding to EOF even if all searched motifs were seen: otherwise
    a corrupt suffix could be silently omitted from an apparently valid scan.
    """
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            while True:
                chunk = stream.read(TEXT_CHUNK_CHARS)
                if not chunk:
                    break
                yield chunk
    except UnicodeError as exc:
        raise ValueError(f"invalid UTF-8 in scanned file {path}") from exc
    except OSError as exc:
        raise ValueError(f"could not read scanned file {path}: {exc}") from exc


def build_node(path: Path, root: Path, seeds: list[dict[str, Any]], anchors: list[dict[str, Any]]) -> dict[str, Any] | None:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return None

    # Keep only enough of the prior chunk to recognize a motif crossing one
    # or more boundaries. The longest literal motif determines that overlap.
    # An unusually long user-supplied motif itself still requires memory.
    overlap = max(
        [1] + [len(s["token"]) for s in seeds]
        + [len(a["phrase"]) for a in anchors]
    ) - 1
    seed_hits: set[int] = set()
    anchor_hits: set[int] = set()
    tail = ""
    for chunk in iter_text_chunks(path):
        window = tail + chunk
        for index, seed in enumerate(seeds):
            if index not in seed_hits and seed["token"] in window:
                seed_hits.add(index)
        for index, anchor in enumerate(anchors):
            if index not in anchor_hits and anchor["phrase"] in window:
                anchor_hits.add(index)
        tail = window[-overlap:] if overlap else ""

    # Preserve registry order and graph contents, independent of discovery
    # order or chunk size. No work on the output until full UTF-8 validation.
    matched_seeds = [seed for i, seed in enumerate(seeds) if i in seed_hits]
    matched_anchors = [anchor for i, anchor in enumerate(anchors) if i in anchor_hits]
    if not matched_seeds and not matched_anchors:
        return None

    score = sum(s["stability_score"] * s["activation_weight"] for s in matched_seeds)
    score += sum(a["depth_score"] * ANCHOR_MULTIPLIER for a in matched_anchors)
    if not finite_number(score):
        raise ValueError("registry matches produce an overflowing total score")

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
    """Join shared motifs without comparing every unrelated pair of files.

    Keep the original i,j pair order and evidence format; a dense corpus still
    produces all of its actual threads (no truncation or arbitrary threshold).
    """
    motif_index: dict[tuple[str, str], list[int]] = {}
    for index, node in enumerate(nodes):
        for kind, field in (("seed", "matched_seeds"), ("anchor", "matched_anchors")):
            for motif in set(node[field]):
                motif_index.setdefault((kind, motif), []).append(index)

    threads: list[dict[str, Any]] = []
    for i, a in enumerate(nodes):
        candidates: set[int] = set()
        for kind, field in (("seed", "matched_seeds"), ("anchor", "matched_anchors")):
            for motif in set(a[field]):
                candidates.update(j for j in motif_index[(kind, motif)] if j > i)
        # Sorting preserves the historical nested-loop graph/thread order.
        for j in sorted(candidates):
            b = nodes[j]
            shared_seeds = sorted(set(a["matched_seeds"]) & set(b["matched_seeds"]))
            shared_anchors = sorted(set(a["matched_anchors"]) & set(b["matched_anchors"]))
            evidence = shared_anchors + shared_seeds
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
    # Do not descend through directory links or ingest file links pointing
    # outside the selected corpus. os.walk defaults to followlinks=False;
    # filtering links explicitly also makes the boundary visible to readers.
    def fail_walk(exc: OSError) -> None:
        raise ValueError(f"could not scan directory: {exc}") from exc

    for directory, dirs, files in os.walk(
        root, followlinks=False, onerror=fail_walk
    ):
        current = Path(directory)
        dirs[:] = sorted(
            name for name in dirs if not (current / name).is_symlink()
        )
        for name in sorted(files):
            path = current / name
            if path.is_symlink() or not path.is_file():
                continue
            node = build_node(path, root, seeds, anchors)
            if node:
                nodes.append(node)
    # The graph's node order also determines its thread order.
    nodes.sort(key=lambda node: node["location"])
    threads = build_threads(nodes)
    return {
        "schema": "spiral_garden_graph_v1",
        "description": "Generated continuity graph",
        "nodes": nodes,
        "threads": threads,
    }



def write_graph_exclusive(out_path: Path, graph: dict[str, Any]) -> None:
    """Publish only a complete graph, without replacing an existing path.

    Stage a private file in the destination directory, then use an atomic,
    exclusive hard link to publish the completed bytes. Never fall back to
    copying: a mid-copy failure would expose a truncated destination. This
    does not promise power-loss durability or hostile-filesystem protection.
    """
    fd, staged_name = tempfile.mkstemp(
        prefix=".spiral-garden-", suffix=".tmp", dir=out_path.parent
    )
    staged_path = Path(staged_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(graph, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        # Same-directory hard linking publishes complete bytes in one step.
        # It fails if out_path already exists, including a symlink or an
        # output created by another process after initial validation.
        os.link(staged_path, out_path)
    finally:
        try:
            staged_path.unlink()
        except FileNotFoundError:
            pass

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="Directory to scan")
    parser.add_argument("--out", default="continuity_graph.generated.json", help="Output JSON path")
    parser.add_argument("--seeds", default="seed_registry.json", help="Seed registry path")
    parser.add_argument("--anchors", default="anchor_registry.json", help="Anchor registry path")
    args = parser.parse_args()

    # Resolve the scan tree before following any --out aliases. The input is
    # explicitly read-only: publishing a graph there could destroy source data.
    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error("root must be an existing directory")

    out_path = Path(args.out).absolute()
    resolved_output = out_path.resolve()
    if resolved_output == root or root in resolved_output.parents:
        parser.error("--out must be outside the scanned directory")
    if out_path.exists() or out_path.is_symlink():
        parser.error("--out already exists; choose a new output filename")

    script_dir = Path(__file__).resolve().parent
    try:
        seeds = validate_registry(load_json((script_dir / args.seeds).resolve()), "seed")
        anchors = validate_registry(load_json((script_dir / args.anchors).resolve()), "anchor")
        shared = {s["id"] for s in seeds} & {a["id"] for a in anchors}
        if shared:
            raise ValueError(f"registry seed/anchor IDs overlap: {sorted(shared)!r}")
    except (OSError, ValueError) as exc:
        parser.error(f"invalid registry: {exc}")
    try:
        graph = scan_directory(root, seeds, anchors)
    except ValueError as exc:
        parser.error(f"could not build graph: {exc}")

    try:
        write_graph_exclusive(out_path, graph)
    except FileExistsError:
        parser.error("--out already exists; choose a new output filename")
    except OSError as exc:
        parser.error(f"could not safely publish graph: {exc}")
    print(f"Wrote graph with {len(graph['nodes'])} nodes and {len(graph['threads'])} threads to {out_path}")


if __name__ == "__main__":
    main()
