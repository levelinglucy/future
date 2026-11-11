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
Matching is **literal and case-sensitive**, including original UTF-8 line breaks:
`\r\n`, `\r` and `\n` are distinct literal sequences, not interchangeable.
Registry JSON terms can express these characters as escaped `\\r` and `\\n`.
A directory with no matches produces an empty graph, which is valid output.

Supply your own JSON-array registries with `--seeds /absolute/path/seeds.json`
and `--anchors /absolute/path/anchors.json`. Entries follow the shipped examples:
seeds need `id`, `token`, `stability_score`, `activation_weight`; anchors need
`id`, `phrase`, `depth_score`. The default paths resolve beside the script,
not relative to the current working directory.

Registry input is checked *before* scanning or creating an output: each registry
must be an array of objects with unique, nonblank string IDs and nonblank
literal match terms. IDs must also be distinct across seeds and anchors so
thread evidence remains unambiguous. Scores and weights must be finite
numbers (not booleans), and a single motif's contribution must not overflow.
Duplicate JSON keys and nonstandard `NaN`/`Infinity` tokens are refused.
Registry IDs and literal match terms must also be representable in UTF-8:
JSON-escaped unpaired surrogate code points are refused *before scanning*
rather than silently becoming impossible matches in a strict UTF-8 corpus.
Ordinary Unicode, including emoji, remains valid; there is no normalization.
If several valid matched contributions overflow the combined score, the
builder refuses the graph rather than writing misleading nonstandard JSON.
These checks do not assign semantic validity to the supplied motifs or weights.

Eligible source files are matched in bounded **64-Ki-character UTF-8 chunks**,
retaining only a longest-motif overlap across chunk boundaries. Matching remains
literal across chunk boundaries (including CRLF and emoji), and the entire file
is decoded even after every motif has matched, so invalid UTF-8 near EOF still
aborts the scan. This reduces temporary **source-text** memory for large files;
very long user-provided motifs, registry definitions, accumulated graph nodes and
dense graph threads may still consume substantial memory. It does not impose
an arbitrary file-size limit or truncate evidence.

Only files with selected text extensions are scanned. Eligible files must
contain valid UTF-8 text: invalid bytes, failed reads and reported directory
traversal errors now abort the scan **without publishing a graph**, instead of
silently dropping bytes or pretending the omitted evidence did not exist.
For other encodings, convert a copy to UTF-8 or select a different corpus.
Output records relative **file paths, matched IDs, and derived scores**,
not full file contents.
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
Thread candidates are indexed by shared motif, avoiding all-pairs comparisons
for sparse corpora while preserving graph IDs, evidence and thread order. Highly
connected corpora can still generate quadratically many output threads and use
significant memory; there is no artificial result truncation.

## One-command disposable walkthrough

From the repository root, run:

```sh
python examples/spiral_garden_demo.py
```

The walkthrough creates two **synthetic** text corpora in a temporary folder,
scans both using the real builder, saves complete graph snapshots under
separate names, reloads them through the strict comparator and saves a full
comparison before printing its short summary. It checks the expected counts:
one file added, one removed, one changed; two connections added and one
changed. All demo files are removed on completion. No historical archive,
personal notes, existing snapshots or network resources are accessed.
It needs Python 3.10+ and a local filesystem permitting hard links; iPhone/
Pythonista hard-link compatibility has **not** been verified. The demonstration
tests software behaviour on contrived data, not the meaning or authenticity
of real-world relationships.

## Compare two saved graph snapshots

Use separate filenames for two builder outputs. To compare their recorded
motifs and graph connections without rescanning either corpus:

```sh
python compare_spiral_gardens.py before.json after.json --out comparison.json
```

For a compact, phone-readable **read-only** overview, use:

```sh
python compare_spiral_gardens.py before.json after.json --summary
```

This prints added, removed and changed node/connection counts, followed by up to
eight quoted paths or path-pairs per change category. Newlines and other control
characters in filenames are escaped, so they cannot impersonate extra report
lines. Longer lists show the number omitted; use the default JSON mode or
`--out` to inspect **every** change. An empty comparison reports no recorded
changes. The `--summary` switch prints to stdout only and cannot be combined
with `--out`, which always saves machine-readable JSON. Like JSON mode, summary
requires both complete, internally consistent input snapshots. It does not
verify chronology or authenticity and may include sensitive filenames.

Use `--out` to publish a **complete comparison to a new filename only**.
It stages private UTF-8 JSON alongside the destination, flushes and fsyncs
the file, then creates the final name exclusively using a hard link.
Existing files and symlinks are never replaced; malformed inputs do not
create an output report. On filesystems that do not support hard links,
publication fails safely without falling back to an incomplete copy.
A killed process can leave a hidden `.spiral-diff-*.tmp` staging file;
review it before removing it. This is not a power-loss durability guarantee,
race-free input snapshot or iPhone/Pythonista compatibility claim.

For interactive inspection, omit `--out` to print JSON on stdout. Ordinary
shell redirection, e.g. `> comparison.json`, **truncates an existing
destination before this program can validate the inputs**. Only use shell
redirection if that overwrite behaviour is deliberate.

The read-only companion produces `spiral_garden_diff_v1` JSON with added,
removed and changed nodes (matched seed/anchor IDs and scores), threads
(type, strength and evidence), and totals. Nodes are compared by their
recorded relative locations and edges by the unordered pair of endpoint
locations. Reordered records and changed internal graph IDs alone are not
changes. A path rename appears as removal plus addition, **not** a move.

Both snapshots must represent comparable scan roots and registry definitions.
Input with duplicate JSON keys, invalid compared fields, non-finite scores,
duplicate IDs/locations or broken thread references is refused without
printing a partial diff. Each thread must additionally agree with both endpoints'
shared motif identifiers: its evidence must include precisely the shared seeds
and anchors in builder order, its connection type must prefer anchors when
present, and its strength must match the builder's formula. A plausible-looking
thread with no genuinely shared motif is rejected. Completeness is checked
too: every pair of files sharing any recorded seed or anchor must have a
corresponding thread. The comparator indexes shared motifs rather than
checking all unrelated node pairs. Missing edges are invalid snapshot data,
not legitimate graph changes. This validates internal
consistency with the v1 builder's rules, **not** whether the graph is authentic,
chronologically accurate or causally meaningful.
Both graphs are loaded into memory; very dense graph files can require
substantial memory. Nothing is written except JSON to stdout (if you redirect
it). Results contain filenames and motif identifiers: treat them as sensitive,
keep them local unless reviewed and avoid sharing blindly.

## Development and change history

**Goal:** publish faithful, complete graph evidence from explicitly selected
local text files, without overwriting source notes or earlier graphs.
**Integration and validation:** [PR #9](https://github.com/levelinglucy/future/pull/9)
tracks the registry UTF-8 preflight and its revision-specific test evidence;
[PR #8](https://github.com/levelinglucy/future/pull/8) is the merged
shared-motif thread-indexing predecessor. Earlier
[PR #7](https://github.com/levelinglucy/future/pull/7),
[PR #6](https://github.com/levelinglucy/future/pull/6),
[PR #5](https://github.com/levelinglucy/future/pull/5), and
[PR #4](https://github.com/levelinglucy/future/pull/4) preserve literal
newlines, strict corpus reads, registry validation and complete publication.
See the exact implementation PR checks;
never treat a successful source scan as proof of power-loss durability.
**Release:** unreleased; no stable tag. **Next:** gather real usability evidence and test any proposed extensions against observed needs.

**Unreleased changes:** add a one-command, temporary synthetic corpus walkthrough exercising actual graph creation, exclusive saved output, strict comparison and readable reports. Earlier: add optional bounded, human-readable `--summary` output while retaining complete JSON comparison and exclusive `--out` saving. Earlier: refuse incomplete graph thread inventories when endpoint matches imply missing links; the comparator detects omissions using a motif index without changing valid diffs or output publication. Earlier: make the read-only comparison reject thread records whose claimed evidence, connection type or strength contradict their recorded endpoint motif matches; valid builder-produced graphs and the diff format remain unchanged. Earlier: add an opt-in complete-only, exclusive `--out` mode for saved graph comparisons, avoiding accidental overwrite/truncation from shell redirection. The existing stdout behaviour is retained. Earlier: add a read-only graph-snapshot comparison command with path-based stable identities, malformed-input refusal and machine-readable change counts. Earlier: stream large eligible source files in bounded text chunks
while preserving exact literal matches, registry order, complete UTF-8 decoding
and graph output schema; reduce per-file temporary allocation without claiming
bounded total graph memory.

Earlier: reject ill-formed Unicode registry IDs and match terms
up front, avoiding misleading no-match graphs from impossible UTF-8 motifs
without rejecting valid emoji or changing literal matching.

Earlier: index thread candidates by shared motif rather than
quadratically comparing unrelated files; preserve the existing graph schema,
thread identities, ordering, evidence and scoring. Sparse large scans become
more practical, but dense graph output remains potentially quadratic.
Earlier changes retain original CRLF, CR and LF sequences while
scanning strict UTF-8 to avoid false positive/negative literal motif matches.
Previously, universal-newline translation changed these characters before matching.
Strict UTF-8 decoding and reported I/O/traversal failures abort graph creation
rather than manufacture matches or hide missing evidence. Earlier registry validation rejects ambiguous, malformed
and overflowing scores; output remains complete-only and exclusive, within
the existing graph schema. Symlinked entries are deliberately skipped.

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

Run `python -m unittest discover -s tests -p 'test_spiral_garden*.py' -v`.
The tests construct disposable input directories and never scan the repository's
historic personal archive. A GitHub Actions smoke workflow runs the same
checks on Python 3.11 and 3.12.

This is a utility for exploring text relationships, not a proof of chronological,
semantic or causal continuity. Historical `continuity_graph.json` remains untouched.
