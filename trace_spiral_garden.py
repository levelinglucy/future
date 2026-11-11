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


def list_locations(graph, contains=None, limit=8, motif=None):
    """Show exact recorded paths, optionally filtering on paths and motif IDs.

    A graph contains only files matching at least one registered motif.
    The path filter is a literal, case-sensitive substring; the motif filter
    is an exact, case-sensitive saved seed or anchor identifier.
    """
    if limit < 1:
        raise ValueError("--limit must be a positive integer")
    if motif == "":
        raise ValueError("--motif must be a nonempty exact identifier")
    nodes, _ = graph
    matching = sorted(
        location for location, details in nodes.items()
        if (contains is None or contains in location)
        and (motif is None or motif in details["matched_seeds"]
             or motif in details["matched_anchors"])
    )
    filters = []
    if contains is not None:
        filters.append(f"case-sensitive path substring {quoted(contains)}")
    if motif is not None:
        filters.append(f"exact motif ID {quoted(motif)}")
    if filters:
        lines = [f"Recorded paths matching {' and '.join(filters)}: "
                 f"{len(matching)} of {len(nodes)}"]
    else:
        lines = [f"{len(nodes)} recorded matching-file locations in this graph"]
    for location in matching[:limit]:
        lines.append("  " + quoted(location))
    if len(matching) > limit:
        lines.append(f"  ... {len(matching) - limit} more; increase --limit to inspect them")
    if not matching:
        lines.append("No recorded paths match the filter." if filters
                     else "No matching-file locations were recorded.")
    lines.append("Only files with literal motif matches appear; other scanned files are absent.")
    return "\n".join(lines)


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
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--from", dest="origin",
                      help="Exact recorded relative location to inspect")
    mode.add_argument("--list", action="store_true",
                      help="List recorded matching-file paths before tracing")
    parser.add_argument("--to", dest="target", help="Optional destination for shortest-hop route")
    parser.add_argument("--contains", help="Literal case-sensitive path substring for --list")
    parser.add_argument("--motif", help="Exact recorded seed or anchor ID for --list")
    parser.add_argument("--limit", type=int, default=8,
                        help="Maximum listed paths or neighbors (default: 8)")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be a positive integer")
    if args.list and args.target is not None:
        parser.error("--to requires --from")
    if not args.list and args.contains is not None:
        parser.error("--contains requires --list")
    if not args.list and args.motif is not None:
        parser.error("--motif requires --list")
    if args.motif == "":
        parser.error("--motif must be a nonempty exact identifier")
    try:
        # The same complete graph validation precedes either output mode.
        from compare_spiral_gardens import load_graph
        graph = load_graph(args.graph)
        report = (list_locations(graph, args.contains, args.limit, args.motif) if args.list
                  else describe(graph, args.origin, args.target, args.limit))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(report)


if __name__ == "__main__":
    main()
