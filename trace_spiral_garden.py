#!/usr/bin/env python3
"""Explore recorded motif connections in one saved Spiral Garden v1 graph.

Read-only: every edge is derived from literal motif IDs, not semantic or
causal evidence. See docs/SPIRAL_GARDEN.md for use and limits.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path


def adjacency_for(nodes, threads):
    """Build an undirected location-keyed adjacency list from validated data."""
    adjacency = {location: {} for location in nodes}
    for (left, right), details in threads.items():
        adjacency[left][right] = details
        adjacency[right][left] = details
    return adjacency


def shortest_path(adjacency, start, target):
    """Fewest edges, with deterministic lexical tie-breaking; None if absent."""
    if start == target:
        return [start]
    queue = deque([start])
    previous = {start: None}
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacency[current]):
            if neighbor in previous:
                continue
            previous[neighbor] = current
            if neighbor == target:
                route = [target]
                while route[-1] != start:
                    route.append(previous[route[-1]])
                return list(reversed(route))
            queue.append(neighbor)
    return None


def quoted(value):
    """Escape control characters in untrusted paths and motif identifiers."""
    return json.dumps(value, ensure_ascii=False)


def render_edge(left, right, details):
    evidence = ", ".join(quoted(motif) for motif in details["evidence"])
    return (f"{quoted(left)} <-> {quoted(right)} | "
            f"via {details['via']} | recorded strength {details['strength']:.3f} "
            f"| shared motifs: {evidence}")


def describe(graph, origin, target=None, limit=8):
    """Describe direct neighbors or one shortest recorded route, never mutate."""
    nodes, threads = graph
    if origin not in nodes:
        raise ValueError(f"location not in saved graph: {quoted(origin)}")
    if target is not None and target not in nodes:
        raise ValueError(f"location not in saved graph: {quoted(target)}")
    if limit < 1:
        raise ValueError("--limit must be a positive integer")
    adjacency = adjacency_for(nodes, threads)
    if target is None:
        linked = sorted(adjacency[origin])
        lines = [f"Direct recorded neighbors of {quoted(origin)}: {len(linked)}"]
        for neighbor in linked[:limit]:
            lines.append("  " + render_edge(origin, neighbor, adjacency[origin][neighbor]))
        if len(linked) > limit:
            lines.append(f"  ... {len(linked) - limit} more; increase --limit to inspect them")
        if not linked:
            lines.append("No recorded direct connection.")
    else:
        route = shortest_path(adjacency, origin, target)
        if route is None:
            lines = [f"No recorded path between {quoted(origin)} and {quoted(target)}."]
        else:
            lines = [f"Shortest recorded path: {len(route) - 1} connection(s)"]
            if len(route) == 1:
                lines.append(f"Same recorded location: {quoted(origin)}")
            for left, right in zip(route, route[1:]):
                lines.append("  " + render_edge(left, right, adjacency[left][right]))
    lines.append("Literal shared-motif links only; not proof of meaning, chronology or causation.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path, help="Saved graph built with build_spiral_garden.py")
    parser.add_argument("--from", dest="origin", required=True,
                        help="Exact recorded relative location to inspect")
    parser.add_argument("--to", dest="target", help="Optional destination for shortest-hop route")
    parser.add_argument("--limit", type=int, default=8, help="Maximum neighbors listed (default: 8)")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be a positive integer")
    try:
        # Reuse the comparator's strict v1 loader: no partial, contradictory or
        # duplicate-key graph can be presented as an authoritative route.
        from compare_spiral_gardens import load_graph
        report = describe(load_graph(args.graph), args.origin, args.target, args.limit)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(report)


if __name__ == "__main__":
    main()
