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
put the output **outside** the scanned tree: the command now refuses
in-tree output to protect scanned source files. It also refuses an already
existing destination (including symlinks) instead of replacing previous
results. For subsequent scans, choose another filename or move the old graph
yourself after reviewing it. Symlinked files could refer
outside a chosen directory. This version skips symlinked files and directories,
so an ordinary link within the selected tree is not scanned or listed in output.
The scanner does not protect against concurrent filesystem replacement/races or
hostile directories: choose a trusted, stable local corpus. Graph nodes and threads
are emitted in sorted path order so repeated runs with unchanged files and
registries produce the same graph structure.

## Development and change history

**Goal:** protect a chosen text corpus from accidental modification during
graph export, while retaining the existing graph schema and literal matching.
**Integration:** [output-safety PR #3](https://github.com/levelinglucy/future/pull/3)
is the validation and decision record; [prior symlink-boundary PR #2](https://github.com/levelinglucy/future/pull/2)
remains historical evidence. **Release:** unreleased maintenance, not a stable
tagged version. **Next:** revisit output durability or hostile filesystem races
only if a real use case needs them.

**Unreleased changes:** refuse in-tree output and existing output paths to avoid
overwriting a scanned document, an earlier graph or a symlink target. The graph
data, registry formats and matcher are unchanged; repeated runs require a fresh
destination name. Previous maintenance skipped symlinked corpus entries and
sorted nodes/threads for reproducible results.

**Boundary:** exclusive file creation prevents replacement of an existing
destination, including one created between the early check and opening. It
does **not** make the generated JSON crash-atomic: if a write fails after the
new output file is opened, a partial file may remain. Inspect or remove that
specific generated file manually before retrying. Concurrent replacement of
corpus directories or their parents is not protected against.

## Verification

Run `python -m unittest discover -s tests -p 'test_spiral_garden.py' -v`.
The tests construct disposable input directories and never scan the repository's
historic personal archive. A GitHub Actions smoke workflow runs the same
checks on Python 3.11 and 3.12.

This is a utility for exploring text relationships, not a proof of chronological,
semantic or causal continuity. Historical `continuity_graph.json` remains untouched.
