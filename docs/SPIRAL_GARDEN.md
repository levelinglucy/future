# Spiral Garden graph builder

`build_spiral_garden.py` is a **local, read-only text scanner** that finds literal
motif matches and writes a JSON graph. The builder uses only Python's standard library
(Python 3.10+). It does not execute scanned code, edit scanned files, contact a server
or infer the meaning/validity of a match.

## Quick start

From a checkout, create a directory of text files you choose to scan, then run:

```sh
python build_spiral_garden.py ./my_notes --out ./spiral-garden-result.json
```

The included `seed_registry.json` and `anchor_registry.json` are small,
illustrative defaults drawn from already-public archive motifs. They let the
documented command work immediately; their numeric weights are arbitrary
example scoring parameters, **not** confidence or evidence of sentience.
Matching is **literal and case-sensitive**. A directory with no matches produces
an empty graph, which is valid output.

Supply your own JSON-array registries with `--seeds /absolute/path/seeds.json`
and `--anchors /absolute/path/anchors.json`. Entries follow the shipped examples:
seeds need `id`, `token`, `stability_score`, `activation_weight`; anchors need
`id`, `phrase`, `depth_score`. The default paths resolve beside the script,
not relative to the current working directory.

Only files with selected text extensions are scanned. Output records relative
**file paths, matched IDs, and derived scores**, not full file contents.
Nevertheless, paths and motif matches can be sensitive. Scan only directories
you are entitled to inspect, keep the output private unless you review it, and
prefer an output location **outside** the scanned tree so subsequent scans do not
accidentally ingest previous generated graphs. Symlinked files could refer
outside a chosen directory. This version skips symlinked files and directories,
so an ordinary link within the selected tree is not scanned or listed in output.
The scanner does not protect against concurrent filesystem replacement/races or
hostile directories: choose a trusted, stable local corpus. Graph nodes and threads
are emitted in sorted path order so repeated runs with unchanged files and
registries produce the same graph structure.

## Development and change history

**Goal:** preserve the explicit scan-root boundary for ordinary local directory
scans without changing the graph schema. **Integration and validation:** tracked
in [Spiral Garden PR #2](https://github.com/levelinglucy/future/pull/2);
a green CI result applies only to the recorded revision and test environment.
**Publication:** this is an untagged maintenance change, not a verified stable
release. **Next:** consider race-resistant file opening only if reading a
concurrently mutating or untrusted directory becomes an actual requirement.

**Unreleased maintenance:** skip symlinked file and directory entries to avoid
accidental inspection of outside documents; sort scanned paths before producing
nodes and threads for deterministic graph output. Prior graph JSON schema and
registry formats are unchanged. A link which formerly matched a motif will now
be absent from the graph; no source or historical archive files are altered.

## Verification

Run `python -m unittest discover -s tests -p 'test_spiral_garden.py' -v`.
The tests construct disposable input directories and never scan the repository's
historic personal archive. A GitHub Actions smoke workflow runs the same
checks on Python 3.11 and 3.12.

This is a utility for exploring text relationships, not a proof of chronological,
semantic or causal continuity. Historical `continuity_graph.json` remains untouched.
