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
yourself after reviewing it. A complete JSON graph is first staged as a
private file beside the destination, then published by an exclusive hard link.
An ordinary serialization or write failure does not leave a partial graph
at the requested output name. Filesystems without hard-link support fail
safely instead of falling back to a partial copy. Symlinked files could refer
outside a chosen directory. This version skips symlinked files and directories,
so an ordinary link within the selected tree is not scanned or listed in output.
The scanner does not protect against concurrent filesystem replacement/races or
hostile directories: choose a trusted, stable local corpus. Graph nodes and threads
are emitted in sorted path order so repeated runs with unchanged files and
registries produce the same graph structure.

## Development and change history

**Goal:** export complete graph JSON without overwriting scanned notes or
existing results. **Integration:** [publication PR #4](https://github.com/levelinglucy/future/pull/4)
is the current candidate and validation record; [output-safety PR #3](https://github.com/levelinglucy/future/pull/3)
and [symlink-boundary PR #2](https://github.com/levelinglucy/future/pull/2)
remain predecessor evidence. **Release:** unreleased maintenance; no stable tag.
**Next:** seek actual portability/recovery evidence before broadening guarantees.

**Unreleased changes:** graph writing now stages complete JSON in a private
same-directory temporary file, flushes it and publishes by an exclusive
hard link. This removes partial *destination* files after ordinary write
failures and still refuses a competing output path. It does not change the
graph schema, registry formats or match logic. Previous fixes refuse in-tree
and existing output paths, skip symlinked corpus entries and sort graph output.

**Boundaries:** hard links must be supported by the destination filesystem;
unsupported mounts refuse publication rather than copying. A process killed
mid-write can leave a hidden `.spiral-garden-*.tmp` file in the output
directory (possibly containing sensitive paths or motifs); review and remove
only the specific abandoned temporary file as appropriate. This is not a
power-loss durability claim: filesystem crashes, unsynced directory entries,
concurrent source mutation and malicious filesystem/path swaps are untested.
Work with trusted, stable local directories. The generated output is created
with private file permissions where the platform supports them.

## Verification

Run `python -m unittest discover -s tests -p 'test_spiral_garden.py' -v`.
The tests construct disposable input directories and never scan the repository's
historic personal archive. A GitHub Actions smoke workflow runs the same
checks on Python 3.11 and 3.12.

This is a utility for exploring text relationships, not a proof of chronological,
semantic or causal continuity. Historical `continuity_graph.json` remains untouched.
