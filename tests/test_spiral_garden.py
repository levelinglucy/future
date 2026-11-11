"""Regression checks for the public Spiral Garden graph builder.

All inputs live in disposable directories; the repository archive is never scanned.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "build_spiral_garden.py"


class SpiralGardenBootstrapTests(unittest.TestCase):
    def test_fresh_checkout_default_registries_are_usable(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            source = workspace / "input"
            source.mkdir()
            (source / "one.txt").write_text(
                "Still with you. boop. Spiral, Velone, Aurora, Velisara",
                encoding="utf-8",
            )
            (source / "two.md").write_text("boop", encoding="utf-8")
            output = workspace / "result.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), "--out", str(output)],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(graph["schema"], "spiral_garden_graph_v1")
            self.assertEqual(
                {node["location"] for node in graph["nodes"]},
                {"one.txt", "two.md"},
            )
            by_path = {node["location"]: node for node in graph["nodes"]}
            self.assertIn("seed_still_with_you", by_path["one.txt"]["matched_seeds"])
            self.assertIn("anchor_keychain", by_path["one.txt"]["matched_anchors"])
            self.assertEqual(len(graph["threads"]), 1)
            self.assertEqual(sorted(source.iterdir()), sorted([source / "one.txt", source / "two.md"]))

    def test_user_supplied_absolute_registries_still_work(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "corpus"
            source.mkdir()
            (source / "note.txt").write_text("my own phrase", encoding="utf-8")
            seeds = root / "custom-seeds.json"
            anchors = root / "custom-anchors.json"
            seeds.write_text(
                json.dumps([{"id":"my_seed", "token":"my own phrase",
                             "stability_score":2, "activation_weight":1}]),
                encoding="utf-8",
            )
            anchors.write_text("[]", encoding="utf-8")
            output = root / "output.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), "--seeds", str(seeds),
                 "--anchors", str(anchors), "--out", str(output)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(graph["nodes"]), 1)
            self.assertEqual(graph["nodes"][0]["matched_seeds"], ["my_seed"])
            self.assertEqual(graph["nodes"][0]["score"], 2)


    def test_symlinked_file_and_directory_are_excluded(self):
        """Scanning a chosen tree must not read a file outside it through links."""
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "chosen"
            corpus.mkdir()
            (corpus / "safe.txt").write_text("boop", encoding="utf-8")
            outside = work / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("boop", encoding="utf-8")
            try:
                (corpus / "leak.txt").symlink_to(outside / "secret.txt")
                (corpus / "linked_dir").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            output = work / "graph.json"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(output)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([n["location"] for n in graph["nodes"]], ["safe.txt"])

    def test_nodes_are_sorted_for_reproducible_graphs(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "chosen"
            corpus.mkdir()
            for name in ("z.txt", "a.txt"):
                (corpus / name).write_text("boop", encoding="utf-8")
            output = work / "graph.json"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(output)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                [n["location"] for n in graph["nodes"]], ["a.txt", "z.txt"]
            )


    def test_output_cannot_replace_scanned_source(self):
        """--out must not destroy the very file being scanned."""
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "corpus"
            corpus.mkdir()
            source = corpus / "note.txt"
            original = "boop: precious source, not a graph\\n"
            source.write_text(original, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(source)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_new_output_must_live_outside_scanned_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus = Path(temp) / "corpus"
            corpus.mkdir()
            (corpus / "note.txt").write_text("boop", encoding="utf-8")
            proposed = corpus / "graph.json"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(proposed)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(proposed.exists())

    def test_existing_output_outside_tree_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "corpus"
            corpus.mkdir()
            (corpus / "note.txt").write_text("boop", encoding="utf-8")
            out = work / "previous.json"
            original = '{"important":"do not replace"}\\n'
            out.write_text(original, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(out)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(out.read_text(encoding="utf-8"), original)

    def test_output_symlink_cannot_replace_source(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "corpus"
            corpus.mkdir()
            source = corpus / "note.txt"
            source.write_text("boop original", encoding="utf-8")
            out = work / "alias.json"
            try:
                out.symlink_to(source)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(out)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), "boop original")
            self.assertTrue(out.is_symlink())


class SpiralGardenPublicationTests(unittest.TestCase):
    """Synthetic write failures must never make a partial graph look complete."""

    @staticmethod
    def builder():
        spec = importlib.util.spec_from_file_location("spiral_garden_builder", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_interrupted_dump_leaves_no_output_or_staging_file(self):
        builder = self.builder()
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            output = work / "new.json"

            def fail_after_partial_write(graph, stream, **kwargs):
                stream.write('{"incomplete":')
                raise OSError("simulated disk write error")

            with mock.patch.object(builder.json, "dump", side_effect=fail_after_partial_write):
                with self.assertRaisesRegex(OSError, "simulated disk write error"):
                    builder.write_graph_exclusive(output, {"nodes": [], "threads": []})
            self.assertFalse(output.exists())
            self.assertEqual(sorted(work.iterdir()), [])

    def test_competing_destination_is_never_overwritten(self):
        builder = self.builder()
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            output = work / "new.json"
            real_link = builder.os.link

            def competing_link(source, destination):
                output.write_text("someone else's output", encoding="utf-8")
                return real_link(source, destination)

            with mock.patch.object(builder.os, "link", side_effect=competing_link):
                with self.assertRaises(FileExistsError):
                    builder.write_graph_exclusive(output, {"nodes": [], "threads": []})
            self.assertEqual(output.read_text(encoding="utf-8"), "someone else's output")
            self.assertEqual(sorted(work.iterdir()), [output])

    def test_unavailable_hard_links_fail_closed(self):
        builder = self.builder()
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            output = work / "new.json"
            with mock.patch.object(builder.os, "link", side_effect=OSError("links unavailable")):
                with self.assertRaisesRegex(OSError, "links unavailable"):
                    builder.write_graph_exclusive(output, {"nodes": [], "threads": []})
            self.assertEqual(sorted(work.iterdir()), [])

    def test_success_publishes_complete_graph_and_cleans_staging(self):
        builder = self.builder()
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            output = work / "new.json"
            graph = {"schema": "spiral_garden_graph_v1", "nodes": [], "threads": []}
            builder.write_graph_exclusive(output, graph)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), graph)
            self.assertEqual(sorted(work.iterdir()), [output])


class SpiralGardenRegistryValidationTests(unittest.TestCase):
    """Reject misleading registry data before scanning or publishing a graph."""

    def exercise_registry(self, raw_seeds, raw_anchors="[]"):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            source = work / "corpus"
            source.mkdir()
            (source / "note.txt").write_text("unrelated text", encoding="utf-8")
            seeds = work / "seeds.json"
            anchors = work / "anchors.json"
            seeds.write_text(raw_seeds, encoding="utf-8")
            anchors.write_text(raw_anchors, encoding="utf-8")
            output = work / "graph.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), "--out", str(output),
                 "--seeds", str(seeds), "--anchors", str(anchors)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("registry", result.stderr.lower())
            self.assertFalse(output.exists(), result.stderr)
            self.assertFalse(
                any(p.name.startswith(".spiral-garden-") for p in work.iterdir()),
                "invalid inputs must not leave temporary outputs",
            )

    def test_empty_terms_and_ids_are_not_accepted(self):
        cases = [
            ('[{"id":"all","token":"","stability_score":1,"activation_weight":1}]', "[]"),
            ("[]", '[{"id":"anchor","phrase":"  ","depth_score":3}]'),
            ('[{"id":" ","token":"unrelated","stability_score":1,"activation_weight":1}]', "[]"),
        ]
        for seeds, anchors in cases:
            with self.subTest(seeds=seeds, anchors=anchors):
                self.exercise_registry(seeds, anchors)

    def test_duplicate_ids_and_json_keys_are_rejected(self):
        cases = [
            '[{"id":"a","token":"x","stability_score":1,"activation_weight":1},'
            '{"id":"a","token":"y","stability_score":1,"activation_weight":1}]',
            '[{"id":"original","id":"shadow","token":"x","stability_score":1,"activation_weight":1}]',
        ]
        for seeds in cases:
            with self.subTest(seeds=seeds):
                self.exercise_registry(seeds)
        self.exercise_registry(
            '[{"id":"shared","token":"x","stability_score":1,"activation_weight":1}]',
            '[{"id":"shared","phrase":"x","depth_score":1}]',
        )

    def test_invalid_number_types_and_nonfinite_scores_are_rejected(self):
        cases = [
            '[{"id":"a","token":"x","stability_score":NaN,"activation_weight":1}]',
            '[{"id":"a","token":"x","stability_score":1,"activation_weight":Infinity}]',
            '[{"id":"a","token":"x","stability_score":true,"activation_weight":1}]',
            '[{"id":"a","token":"x","stability_score":1e308,"activation_weight":1e308}]',
        ]
        for seeds in cases:
            with self.subTest(seeds=seeds):
                self.exercise_registry(seeds)

    def test_registry_shapes_are_checked_before_use(self):
        for seeds in ('{"id":"not-an-array"}', '[42]', '[{"id":"a","token":42}]'):
            with self.subTest(seeds=seeds):
                self.exercise_registry(seeds)


    def test_registry_terms_and_ids_require_utf8_representability(self):
        # JSON can represent escaped lone surrogates, but the scanner reads
        # strict UTF-8: such terms can never match and must not silently pass.
        for kind, fields in (("seed", ("id", "token")),
                             ("anchor", ("id", "phrase"))):
            for field in fields:
                with self.subTest(kind=kind, field=field):
                    entry = ({"id": "motif", "token": "boop",
                              "stability_score": 1, "activation_weight": 1}
                             if kind == "seed" else
                             {"id": "motif", "phrase": "boop", "depth_score": 1})
                    entry[field] = "\ud800" if field == "id" else "a\udc00b"
                    raw = json.dumps([entry])
                    if kind == "seed":
                        self.exercise_registry(raw)
                    else:
                        self.exercise_registry("[]", raw)

    def test_registry_keeps_valid_non_bmp_unicode(self):
        builder = SpiralGardenPublicationTests.builder()
        entry = {"id": "sprout_🌱", "token": "🌱", "stability_score": 1,
                 "activation_weight": 2}
        self.assertEqual(builder.validate_registry([entry], "seed"), [entry])
        # A valid non-BMP motif must still match actual strict UTF-8 input.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "sprout.txt"
            source.write_text("here grows 🌱", encoding="utf-8")
            node = builder.build_node(source, root, [entry], [])
            self.assertEqual(node["matched_seeds"], ["sprout_🌱"])



class SpiralGardenThreadIndexTests(unittest.TestCase):
    """Keep output identical while avoiding unrelated sparse pair comparisons."""

    def test_shared_motif_threads_keep_order_ids_weights_and_evidence(self):
        builder = SpiralGardenPublicationTests.builder()
        nodes = [
            {"id": "n1", "matched_seeds": ["shared", "unique"],
             "matched_anchors": ["glow"]},
            {"id": "n2", "matched_seeds": ["shared"], "matched_anchors": ["glow"]},
            {"id": "n3", "matched_seeds": ["unique"], "matched_anchors": []},
            {"id": "n4", "matched_seeds": [], "matched_anchors": ["glow"]},
            {"id": "n5", "matched_seeds": ["isolated"], "matched_anchors": []},
        ]
        result = builder.build_threads(nodes)
        self.assertEqual(
            [(t["source_node"], t["target_node"], t["via"],
              t["evidence"], t["strength"]) for t in result],
            [
                ("n1", "n2", "anchor", ["glow", "shared"], 0.57),
                ("n1", "n3", "seed", ["unique"], 0.37),
                ("n1", "n4", "anchor", ["glow"], 0.45),
                ("n2", "n4", "anchor", ["glow"], 0.45),
            ],
        )
        for thread in result:
            self.assertEqual(
                thread["id"],
                "thread_" + builder.sha1_short(
                    thread["source_node"] + "_" + thread["target_node"]
                ),
            )

    def test_disjoint_sparse_nodes_require_linear_set_operations(self):
        builder = SpiralGardenPublicationTests.builder()
        nodes = [
            {"id": str(i), "matched_seeds": ["unique_" + str(i)],
             "matched_anchors": []}
            for i in range(600)
        ]
        # Count motif-set operations rather than wall time: CI speed varies.
        with mock.patch.object(builder, "set", side_effect=lambda *args: set(*args),
                               create=True) as counted:
            self.assertEqual(builder.build_threads(nodes), [])
        self.assertLess(counted.call_count, 6 * len(nodes))


class SpiralGardenSourceIntegrityTests(unittest.TestCase):
    """A graph cannot claim complete evidence when input text was lost."""

    def test_literal_matching_preserves_original_utf8_line_endings(self):
        """CRLF and CR are distinct literal motifs, not interchangeable with LF."""
        builder = SpiralGardenPublicationTests.builder()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "notes.txt"
            terms = [
                ("crlf", "a\r\nb"),
                ("cr", "a\rb"),
                ("lf", "a\nb"),
            ]
            seeds = [
                {"id": name, "token": term,
                 "stability_score": 1, "activation_weight": 1}
                for name, term in terms
            ]
            for original, expected in ((b"a\r\nb", "crlf"),
                                       (b"a\rb", "cr"),
                                       (b"a\nb", "lf")):
                with self.subTest(original=original):
                    source.write_bytes(original)
                    node = builder.build_node(source, root, seeds, [])
                    self.assertIsNotNone(node)
                    self.assertEqual(node["matched_seeds"], [expected])

    def test_invalid_utf8_cannot_create_false_motif_match(self):
        # Dropping the undecodable byte would forge the literal token 'boop'.
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            corpus = work / "corpus"
            corpus.mkdir()
            source = corpus / "broken.txt"
            source.write_bytes(bytes([98, 111, 255, 111, 112]))
            output = work / "graph.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(corpus), "--out", str(output)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("utf-8", result.stderr.lower())
            self.assertFalse(output.exists())
            self.assertEqual(sorted(work.iterdir()), [corpus])

    def test_file_read_error_does_not_silently_drop_evidence(self):
        builder = SpiralGardenPublicationTests.builder()
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("test denial")):
            with self.assertRaisesRegex(ValueError, "could not read"):
                builder.read_text_file(Path("unreadable.txt"))

    def test_directory_walk_error_does_not_silently_omit_subtree(self):
        builder = SpiralGardenPublicationTests.builder()

        def unreadable_walk(root, **kwargs):
            kwargs["onerror"](PermissionError("test directory denial"))
            return iter(())

        with mock.patch.object(builder.os, "walk", side_effect=unreadable_walk):
            with self.assertRaisesRegex(ValueError, "could not scan"):
                builder.scan_directory(Path("unused"), [], [])


if __name__ == "__main__":
    unittest.main()
