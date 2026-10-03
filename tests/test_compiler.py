import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_ROOT = Path(__file__).resolve().parents[1]
PARSER_ROOT = TOOLS_ROOT / "parser"
FIXTURES = TOOLS_ROOT / "tests" / "fixtures" / "0.5.0"
ROOT_SPEC = TOOLS_ROOT.parent / "syntax" / "0.5.0"
sys.path.insert(0, str(PARSER_ROOT))

from compiler import compile_paths  # noqa: E402
from validation import validate_interchange  # noqa: E402


def deck_source(
    *,
    labels="english;japanese",
    side_zero="[food:english] is ready.",
    side_one="[food:japanese]です。",
    extra_selectables="",
    groups="food;item;key;{apple}",
    vocabulary="",
    ending="\n",
):
    return (
        "# Selectables\n"
        "## item\n"
        ">key;english;japanese\n"
        "apple;apple;りんご\n"
        f"{extra_selectables}"
        "# Groups\n"
        f"{groups}\n"
        "# Templates\n"
        "## lesson_1\n"
        f">{labels}\n"
        f"{vocabulary}"
        "{\n"
        f"    {side_zero}\n"
        f"    {side_one}\n"
        "}"
        f"{ending}"
    )


class CompilerTestCase(unittest.TestCase):
    def compile_files(self, files):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, contents in files:
                path = Path(directory) / name
                if isinstance(contents, bytes):
                    path.write_bytes(contents)
                else:
                    with path.open("w", encoding="utf-8", newline="") as source_file:
                        source_file.write(contents)
                paths.append(path)
            return compile_paths(paths)

    def compile_text(self, source, name="deck.lacu"):
        return self.compile_files([(name, source)])

    def assert_error(self, result, fragment):
        self.assertTrue(result.has_errors)
        self.assertIsNone(result.document)
        messages = "\n".join(item.message for item in result.diagnostics)
        self.assertIn(fragment, messages)

    def assert_warning(self, result, fragment):
        self.assertFalse(result.has_errors)
        messages = "\n".join(
            item.message for item in result.diagnostics if item.severity == "warning"
        )
        self.assertIn(fragment, messages)


class ReferenceExampleTests(CompilerTestCase):
    def test_complete_example_matches_expected_interchange(self):
        result = compile_paths([FIXTURES / "complete.lacu"])
        self.assertFalse(result.has_errors)
        self.assertEqual(
            result.document,
            json.loads((FIXTURES / "complete.json").read_text(encoding="utf-8")),
        )

    def test_layered_example_matches_expected_interchange(self):
        result = compile_paths(
            [FIXTURES / "layer-base.lacu", FIXTURES / "layer-extension.lacu"]
        )
        self.assertFalse(result.has_errors)
        self.assertEqual(
            result.document,
            json.loads((FIXTURES / "layered.json").read_text(encoding="utf-8")),
        )
        warnings = [item.message for item in result.diagnostics]
        self.assertTrue(any("duplicate Selectable" in message for message in warnings))
        self.assertTrue(any("redundant member" in message for message in warnings))
        self.assertTrue(any("repeated vocabulary" in message for message in warnings))

    def test_copied_specification_files_match_root_when_available(self):
        if not ROOT_SPEC.exists():
            self.skipTest("root specification checkout is unavailable")
        pairs = [
            (PARSER_ROOT / "syntax/0.5.0/interchange.schema.json", ROOT_SPEC / "interchange.schema.json"),
        ]
        for filename in (
            "complete.lacu",
            "complete.json",
            "layer-base.lacu",
            "layer-extension.lacu",
            "layered.json",
            "diagnostics.md",
            "invalid-extra-property.json",
            "semantic-invalid-side-labels.json",
            "invalid-first-supplementary.json",
        ):
            pairs.append((FIXTURES / filename, ROOT_SPEC / "examples" / filename))
        for local, authoritative in pairs:
            with self.subTest(filename=local.name):
                self.assertEqual(local.read_bytes(), authoritative.read_bytes())


class SourceDecodingTests(CompilerTestCase):
    def test_lf_crlf_and_legacy_extension_are_accepted(self):
        lf = deck_source()
        crlf = lf.replace("\n", "\r\n")
        for name, source in (("deck.lacu", lf), ("deck.lacu", crlf), ("deck.md", lf)):
            with self.subTest(name=name, ending="crlf" if "\r" in source else "lf"):
                result = self.compile_text(source, name)
                self.assertFalse(result.has_errors)

    def test_missing_final_line_ending_warns_and_compiles(self):
        result = self.compile_text(deck_source(ending=""))
        self.assert_warning(result, "no line ending")

    def test_bom_invalid_utf8_and_bare_carriage_return_are_errors(self):
        valid = deck_source().encode()
        cases = [
            (b"\xef\xbb\xbf" + valid, "byte-order"),
            (valid + b"\xff", "not valid UTF-8"),
            (valid.replace(b"\n", b"\r", 1), "bare carriage"),
        ]
        for raw, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assert_error(self.compile_text(raw), fragment)

    def test_indented_comments_are_ignored_and_html_comment_must_close(self):
        source = deck_source().replace(
            "# Groups\n", "  // unrestricted [&+] text\n\t<!-- more [&+] text -->\n# Groups\n"
        )
        self.assertFalse(self.compile_text(source).has_errors)
        broken = source.replace("<!-- more [&+] text -->", "<!-- not closed")
        self.assert_error(self.compile_text(broken), "missing its closing")

    def test_csv_quoting_is_single_line_and_strict(self):
        valid = deck_source().replace(
            "apple;apple;りんご",
            'apple;"contains; a semicolon";"She said ""hello""."',
        )
        result = self.compile_text(valid)
        self.assertFalse(result.has_errors)
        self.assertEqual(
            result.document["categories"][0]["selectables"][0]["variants"][1:],
            ["contains; a semicolon", 'She said "hello".'],
        )
        for source in (
            deck_source().replace("apple;apple;りんご", 'apple;"unclosed;value'),
            deck_source().replace("apple;apple;りんご", 'apple;bad"quote;りんご'),
        ):
            with self.subTest(source=source.splitlines()[3]):
                self.assert_error(self.compile_text(source), "quote")

    def test_side_indentation_is_removed_but_trailing_spaces_are_preserved(self):
        source = deck_source(
            side_zero='"[food:english] has; punctuation.  "',
            side_one="[food:japanese]です。",
        )
        result = self.compile_text(source)
        self.assert_warning(result, "trailing ASCII spaces in a Template Side")
        self.assertEqual(
            result.document["chapters"][0]["templates"][0]["sides"][0],
            "[food:english] has; punctuation.  ",
        )

    def test_selectable_trailing_spaces_are_preserved_and_warn(self):
        result = self.compile_text(
            deck_source().replace("apple;apple;りんご", "apple;apple ;りんご")
        )
        self.assert_warning(result, "Selectable Variant value")
        self.assertEqual(
            result.document["categories"][0]["selectables"][0]["variants"][1],
            "apple ",
        )

    def test_unquoted_semicolon_creates_multiple_side_fields_and_fails(self):
        self.assert_error(
            self.compile_text(deck_source(side_zero="[food]; extra")),
            "exactly one field",
        )


class StructureAndLayeringTests(CompilerTestCase):
    def test_empty_selectables_and_groups_support_fixed_text_deck(self):
        source = (
            "# Selectables\n"
            "# Groups\n"
            "# Templates\n"
            "## lesson\n"
            ">english\n"
            "{\n"
            "    Hello.\n"
            "}\n"
        )
        result = self.compile_text(source)
        self.assertFalse(result.has_errors)
        self.assertEqual(result.document["categories"], [])
        self.assertEqual(result.document["groups"], [])

    def test_required_section_order_and_unknown_headers_are_enforced(self):
        cases = [
            (deck_source().replace("# Groups\n", ""), "required '# Groups'"),
            (deck_source().replace("# Groups\n", "# Templates\n# Groups\n"), "out of order"),
            (deck_source().replace("# Groups\n", "# Unknown\n# Groups\n"), "unknown top-level"),
            (deck_source().replace("# Groups\n", "# Groups\n# Groups\n"), "occurs more than once"),
        ]
        for source, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assert_error(self.compile_text(source), fragment)

    def test_brace_and_outside_text_errors(self):
        cases = [
            (deck_source().replace("{\n", "{\n{\n"), "cannot be nested"),
            (deck_source()[:-2], "not closed"),
            (deck_source().replace("{\n", "}\n{\n"), "no matching"),
            (deck_source().replace("[food:english] is ready.\n", ""), "expected 2"),
            (deck_source().replace("{\n", "{\n}\n{\n"), "at least one Side"),
            (deck_source().replace("{\n", "outside\n{\n"), "outside a Template"),
        ]
        for source, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assert_error(self.compile_text(source), fragment)

    def test_category_schema_redefinition_is_error_and_contributes_no_rows(self):
        prior = deck_source()
        extension = deck_source(extra_selectables="banana;banana;バナナ\n").replace(
            ">key;english;japanese", ">key;english"
        )
        self.assert_error(
            self.compile_files([("base.lacu", prior), ("extension.lacu", extension)]),
            "different ordered Variant schema",
        )

    def test_initial_and_layered_duplicate_selectables_warn(self):
        initial = deck_source(extra_selectables="apple;apple;りんご\n")
        self.assert_warning(self.compile_text(initial), "duplicate Selectable")
        layered = self.compile_files(
            [("one.lacu", deck_source()), ("two.lacu", deck_source())]
        )
        self.assert_error(layered, "duplicate Chapter")
        self.assertTrue(
            any("duplicate Selectable" in item.message for item in layered.diagnostics)
        )

    def test_group_extension_deduplicates_members_in_order(self):
        source = deck_source(
            extra_selectables="banana;banana;バナナ\n",
            groups="food;item;key;{apple,apple}\nfood;item;key;{apple,banana}",
        )
        result = self.compile_text(source)
        self.assertFalse(result.has_errors)
        self.assertEqual(result.document["groups"][0]["keys"], ["apple", "banana"])
        self.assertGreaterEqual(
            sum("redundant member" in item.message for item in result.diagnostics), 2
        )

    def test_forward_reference_resolves_against_later_layer(self):
        prior = deck_source().replace(
            "apple;apple;りんご\n", "banana;banana;バナナ\n"
        ).replace("{apple}", "{apple}")
        later = deck_source().replace("## lesson_1", "## lesson_2")
        result = self.compile_files([("prior.lacu", prior), ("later.lacu", later)])
        self.assertFalse(result.has_errors)
        self.assertEqual(result.document["groups"][0]["keys"], ["apple"])

    def test_pairgroup_state_does_not_leak_to_file_without_pairgroups(self):
        pair_source = deck_source(
            groups="food;item;key;{apple}\nother;item;key;{apple}",
        ).replace(
            "# Templates",
            "# Pair Groups\n## relation\n>a=group;b=group\nfood;other\n# Templates",
        )
        second = deck_source().replace("## lesson_1", "## lesson_2")
        result = self.compile_files([("one.lacu", pair_source), ("two.lacu", second)])
        self.assertFalse(result.has_errors)
        self.assertEqual(len(result.document["pair_groups"]), 1)


class DeclarationAndTemplateTests(CompilerTestCase):
    def test_structural_names_and_content_characters_are_validated(self):
        self.assert_error(
            self.compile_text(deck_source().replace("## item", "## bad-name")),
            "valid structural name",
        )
        for character, advice in (("&", "spell out 'and'"), ("+", "spell out 'plus'")):
            with self.subTest(character=character):
                result = self.compile_text(deck_source(side_zero=f"A {character} B."))
                self.assert_error(result, advice)
        self.assert_error(
            self.compile_text(deck_source(side_zero="Use “curly quotes”.")),
            "forbidden literal",
        )

    def test_ambiguous_lookup_warns_and_uses_first(self):
        source = deck_source(
            extra_selectables="apple;second apple;アップル\n",
        )
        result = self.compile_text(source)
        self.assert_warning(result, "ambiguous lookup")
        self.assertEqual(result.document["groups"][0]["keys"], ["apple"])

    def test_member_list_shape_and_empty_values_are_rejected(self):
        for replacement in ("apple", "{}", "{apple,}", "{apple,{banana}}"):
            with self.subTest(replacement=replacement):
                source = deck_source(groups=f"food;item;key;{replacement}")
                self.assert_error(self.compile_text(source), "member list")
        self.assert_error(
            self.compile_text(deck_source().replace("apple;apple;りんご", "apple;;りんご")),
            "must not be empty",
        )

    def test_repeated_vocabulary_is_deduplicated_by_selectable_identity(self):
        source = deck_source(
            vocabulary=(
                ">vocab;item;key;{apple}\n"
                ">vocab;item;english;{apple}\n"
            )
        )
        result = self.compile_text(source)
        self.assert_warning(result, "repeated vocabulary")
        self.assertEqual(len(result.document["chapters"][0]["vocab"]), 1)

    def test_side_labels_and_forced_side_reorder_together(self):
        source = deck_source(
            labels="english;^japanese;~notes",
            side_one="[food:japanese]です。",
        ).replace(
            "    [food:japanese]です。\n}\n",
            "    [food:japanese]です。\n    [food:english] note.\n}\n",
        )
        result = self.compile_text(source)
        self.assertFalse(result.has_errors)
        chapter = result.document["chapters"][0]
        self.assertEqual(chapter["column_variants"], ["japanese", "english", "~notes"])
        self.assertEqual(chapter["forced_first_side"], 1)
        self.assertEqual(chapter["templates"][0]["sides"][0], "[food:japanese]です。")

    def test_invalid_side_label_forms_fail(self):
        cases = [
            ("english;english", "unique"),
            ("english;~english", "unique"),
            ("^english;^japanese", "at most one"),
            ("^~english;japanese", "combines"),
            ("~english;~japanese", "non-supplementary"),
            ("~english;japanese", "first Side"),
        ]
        for labels, fragment in cases:
            with self.subTest(labels=labels):
                self.assert_error(self.compile_text(deck_source(labels=labels)), fragment)

    def test_repeated_and_later_only_selections_fail(self):
        repeated = deck_source(side_zero="[food] and [food:japanese].")
        self.assert_error(self.compile_text(repeated), "more than once")
        later = deck_source(side_zero="Fixed text.")
        self.assert_error(self.compile_text(later), "absent from compiled Side zero")

    def test_later_sides_may_omit_or_reorder_side_zero_selections(self):
        source = deck_source(
            groups="food;item;key;{apple}\nother;item;key;{apple}",
            side_zero="[food] and [other].",
            side_one="[other:japanese]です。",
        )
        self.assertFalse(self.compile_text(source).has_errors)

    def test_malformed_replacement_and_unknown_variant_fail(self):
        cases = [
            ("[food", "unclosed replacement"),
            ("[food:english:extra]", "malformed group"),
            ("[food:no_such_variant]", "unknown Variant"),
            ("Use [literal brackets].", "malformed group"),
            ("text]", "unmatched replacement"),
        ]
        for side, fragment in cases:
            with self.subTest(side=side):
                self.assert_error(self.compile_text(deck_source(side_zero=side)), fragment)

    def pairgroup_source(self, columns="a=group;b=selectable:item:key", row="food;apple"):
        return deck_source().replace(
            "# Templates",
            f"# Pair Groups\n## relation\n>{columns}\n{row}\n# Templates",
        ).replace("[food:english]", "<relation:a:english>").replace(
            "[food:japanese]", "<relation:a:japanese>"
        )

    def test_pairgroup_column_count_row_width_alias_and_variant_checks(self):
        cases = [
            (self.pairgroup_source(columns="a=group"), "at least two columns"),
            (self.pairgroup_source(row="food"), "expected 2"),
            (self.pairgroup_source(columns="a=group;a=group", row="food;food"), "aliases must be unique"),
            (
                self.pairgroup_source().replace("<relation:a:english>", "<relation:missing:english>"),
                "unknown alias",
            ),
            (
                self.pairgroup_source().replace("<relation:a:english>", "<relation:a:missing>"),
                "unknown Variant",
            ),
        ]
        for source, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assert_error(self.compile_text(source), fragment)

    def test_more_than_one_pairgroup_across_template_is_error(self):
        source = self.pairgroup_source().replace(
            "# Templates",
            "## second\n>x=group;y=selectable:item:key\nfood;apple\n# Templates",
        ).replace(
            "<relation:a:japanese>",
            "<second:x:japanese>",
        )
        self.assert_error(self.compile_text(source), "only one distinct Pairgroup")

    def test_pairgroups_cannot_be_reopened_across_layers(self):
        first = self.pairgroup_source()
        second = self.pairgroup_source().replace("## lesson_1", "## lesson_2")
        self.assert_error(
            self.compile_files([("one.lacu", first), ("two.lacu", second)]),
            "cannot be reopened",
        )


class InterchangeValidationTests(unittest.TestCase):
    def load(self, name):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_known_invalid_examples_are_rejected(self):
        expected = {
            "invalid-extra-property.json": "syntax_version",
            "invalid-first-supplementary.json": "does not match",
            "semantic-invalid-side-labels.json": "duplicate Side labels",
        }
        for filename, fragment in expected.items():
            with self.subTest(filename=filename):
                self.assertIn(fragment, "\n".join(validate_interchange(self.load(filename))))

    def test_cross_field_lengths_and_derived_fields_are_checked(self):
        valid = self.load("complete.json")
        mutations = []
        item = copy.deepcopy(valid)
        item["categories"][0]["num_variants"] = 99
        mutations.append((item, "num_variants"))
        item = copy.deepcopy(valid)
        item["categories"][0]["selectables"][0]["variants"].pop()
        mutations.append((item, "variants"))
        item = copy.deepcopy(valid)
        item["pair_groups"][0]["category_checking"][0] = "color"
        mutations.append((item, "category_checking"))
        item = copy.deepcopy(valid)
        item["chapters"][0]["templates"][0]["sides"].pop()
        mutations.append((item, "sides"))
        item = copy.deepcopy(valid)
        item["groups"][0]["keys"][0] = "Alice,Bob"
        mutations.append((item, "cannot contain commas"))
        for document, fragment in mutations:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, "\n".join(validate_interchange(document)))

    def test_schema_invalid_value_shapes_return_errors_without_raising(self):
        valid = self.load("complete.json")
        mutations = []
        item = copy.deepcopy(valid)
        item["groups"][0]["category_name"] = []
        mutations.append(item)
        item = copy.deepcopy(valid)
        item["pair_groups"][0]["pairs"][0][0] = []
        mutations.append(item)
        item = copy.deepcopy(valid)
        item["chapters"][0]["column_variants"][0] = []
        mutations.append(item)
        for document in mutations:
            with self.subTest(document=document):
                self.assertTrue(validate_interchange(document))


class CommandTests(CompilerTestCase):
    SCRIPT = PARSER_ROOT / "lacu_parse.py"

    def run_command(self, args, cwd=None):
        return subprocess.run(
            [sys.executable, str(self.SCRIPT), *map(str, args)],
            cwd=cwd,
            text=True,
            capture_output=True,
        )

    def test_success_warnings_and_errors_keep_streams_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            good = directory / "good.lacu"
            warning = directory / "warning.lacu"
            bad = directory / "bad.lacu"
            good.write_text(deck_source(), encoding="utf-8")
            warning.write_text(deck_source(ending=""), encoding="utf-8")
            bad.write_text("# Unknown\n", encoding="utf-8")
            result = self.run_command([good], cwd=directory)
            self.assertEqual(result.returncode, 0)
            json.loads(result.stdout)
            self.assertEqual(result.stderr, "")
            result = self.run_command([warning], cwd=directory)
            self.assertEqual(result.returncode, 0)
            json.loads(result.stdout)
            self.assertIn("warning:", result.stderr)
            result = self.run_command([bad], cwd=directory)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn(f"{bad}:1: error:", result.stderr)

    def test_invalid_prior_file_is_nonzero_and_emits_no_json(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            prior = directory / "prior.lacu"
            primary = directory / "primary.lacu"
            prior.write_text("# Unknown\n", encoding="utf-8")
            primary.write_text(deck_source(), encoding="utf-8")
            result = self.run_command([primary, "-f", prior])
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn(str(prior), result.stderr)

    def test_file_access_error_is_nonzero_and_emits_no_json(self):
        missing = TOOLS_ROOT / "tests" / "does-not-exist.lacu"
        result = self.run_command([missing])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("cannot read source file", result.stderr)

    def test_diagnostic_options_never_contaminate_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "deck.lacu"
            source.write_text(deck_source(), encoding="utf-8")
            for options in (["-v"], ["-l"], ["-d"], ["-v", "-l", "-d"]):
                with self.subTest(options=options):
                    result = self.run_command([source, *options])
                    self.assertEqual(result.returncode, 0)
                    json.loads(result.stdout)
                    if "-v" in options or "-l" in options:
                        self.assertIn("info:", result.stderr)
            result = self.run_command([source, "--issues-only", "-v", "-l"])
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("info:", result.stderr)


if __name__ == "__main__":
    unittest.main()
