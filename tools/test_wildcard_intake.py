#!/usr/bin/env python3
"""Unit tests for tools/wildcard_intake.py.

The point of these tests is the selection predicate, because a wrong answer
here is silent: an over-eager match labels a non-proposal issue (misrouting
triage), and an under-eager one leaves a proposal unlabeled (the exact bug
this exists to fix — 12 unlabeled proposals, 0 of them in the ledger).

The template is read from a temporary directory, so the tests pin the
contract rather than whatever the real form happens to say today.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import wildcard_intake as wi

REAL_TEMPLATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir,
    ".github", "ISSUE_TEMPLATE", "wildcard.yml",
)


def write_template(root, body):
    d = os.path.join(root, ".github", "ISSUE_TEMPLATE")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "wildcard.yml"), "w", encoding="utf-8") as f:
        f.write(body)


def issue(number, title, labels=(), pull_request=False):
    it = {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in labels],
    }
    if pull_request:
        it["pull_request"] = {"url": "https://example.invalid/pr"}
    return it


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_reads_declared_labels_and_title_prefix(self):
        write_template(
            self.root,
            'name: Wildcard proposal ($500 track)\n'
            'title: "[wildcard] "\n'
            'labels: ["wildcard", "💎 Bounty"]\n'
            "body:\n"
            "  - type: markdown\n",
        )
        self.assertEqual(wi.declared_labels(self.root), ["wildcard", "💎 Bounty"])
        self.assertEqual(wi.title_prefix(self.root), "[wildcard] ")

    def test_missing_template_is_an_error_not_an_empty_list(self):
        # Fail closed: silently returning [] would let the workflow apply
        # nothing and report success, which is the bug in a new costume.
        with self.assertRaises(wi.TemplateError):
            wi.declared_labels(self.root)

    def test_template_without_labels_key_is_an_error(self):
        write_template(self.root, 'name: x\ntitle: "[wildcard] "\nbody:\n')
        with self.assertRaises(wi.TemplateError):
            wi.declared_labels(self.root)

    def test_empty_label_list_is_an_error(self):
        write_template(self.root, 'title: "[wildcard] "\nlabels: []\nbody:\n')
        with self.assertRaises(wi.TemplateError):
            wi.declared_labels(self.root)

    def test_non_list_labels_is_an_error(self):
        write_template(self.root, 'title: "[wildcard] "\nlabels: wildcard\nbody:\n')
        with self.assertRaises(wi.TemplateError):
            wi.declared_labels(self.root)

    def test_body_lines_are_not_parsed_as_frontmatter(self):
        # A `labels:` key inside the body must not shadow the frontmatter.
        write_template(
            self.root,
            'title: "[wildcard] "\n'
            'labels: ["wildcard"]\n'
            "body:\n"
            "  - type: markdown\n"
            "    attributes:\n"
            "      value: |\n"
            "        labels: [nope]\n",
        )
        self.assertEqual(wi.declared_labels(self.root), ["wildcard"])


class SelectionTests(unittest.TestCase):
    LABELS = ["wildcard", "💎 Bounty"]
    PREFIX = "[wildcard] "

    def test_unlabeled_wildcard_proposal_is_selected(self):
        sel = wi.select([issue(565, "[wildcard] Make the Go toolchain the oracle")],
                        self.LABELS, self.PREFIX)
        self.assertEqual(sel, [(565, ["wildcard", "💎 Bounty"])])

    def test_partially_labeled_proposal_gets_only_the_missing_label(self):
        sel = wi.select(
            [issue(1, "[wildcard] x", labels=["wildcard"])], self.LABELS, self.PREFIX)
        self.assertEqual(sel, [(1, ["💎 Bounty"])])

    def test_fully_labeled_proposal_is_not_selected(self):
        sel = wi.select(
            [issue(1, "[wildcard] x", labels=self.LABELS)], self.LABELS, self.PREFIX)
        self.assertEqual(sel, [])

    def test_non_wildcard_title_is_not_selected(self):
        # The form is what declares these labels. A plain issue that happens
        # to lack them was not filed as a proposal.
        sel = wi.select([issue(9, "[soundness] P2: something")], self.LABELS, self.PREFIX)
        self.assertEqual(sel, [])

    def test_prefix_must_match_at_the_start(self):
        sel = wi.select([issue(9, "re: [wildcard] x")], self.LABELS, self.PREFIX)
        self.assertEqual(sel, [])

    def test_pull_requests_are_never_selected(self):
        sel = wi.select(
            [issue(1, "[wildcard] x", pull_request=True)], self.LABELS, self.PREFIX)
        self.assertEqual(sel, [])

    def test_issue_with_no_labels_key_is_selected(self):
        sel = wi.select([{"number": 2, "title": "[wildcard] y"}], self.LABELS, self.PREFIX)
        self.assertEqual(sel, [(2, ["wildcard", "💎 Bounty"])])

    def test_selection_preserves_input_order(self):
        issues = [issue(3, "[wildcard] c"), issue(1, "[wildcard] a"), issue(2, "[wildcard] b")]
        self.assertEqual([n for n, _ in wi.select(issues, self.LABELS, self.PREFIX)],
                         [3, 1, 2])


class CliShapeTests(unittest.TestCase):
    """`--select` must accept the shape each workflow job actually pipes in.

    The on-open job pipes `gh issue view --json ...`, which is ONE object; the
    backfill pipes `gh issue list --json ...`, which is a LIST. An earlier
    draft accepted only the list, so the on-open job died with
    "stdin JSON must be a list of issues" the moment a real issue arrived.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        write_template(
            self.root,
            'title: "[wildcard] "\nlabels: ["wildcard", "💎 Bounty"]\nbody:\n',
        )
        self.tool = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "wildcard_intake.py")

    def run_tool(self, stdin):
        return subprocess.run(
            [sys.executable, self.tool, "--root", self.root, "--select"],
            input=stdin, capture_output=True, text=True, encoding="utf-8",
        )

    def test_single_object_from_gh_issue_view(self):
        payload = json.dumps(issue(565, "[wildcard] x"))
        r = self.run_tool(payload)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "565:wildcard,💎 Bounty")

    def test_list_from_gh_issue_list(self):
        payload = json.dumps([issue(1, "[wildcard] a"), issue(2, "[wildcard] b")])
        r = self.run_tool(payload)
        self.assertEqual(r.returncode, 0, r.stderr)
        # splitlines, not split: one label contains a space, so the line is
        # "1:wildcard,💎 Bounty" and whitespace-splitting would cut it in two.
        self.assertEqual(r.stdout.splitlines(),
                         ["1:wildcard,💎 Bounty", "2:wildcard,💎 Bounty"])

    def test_single_non_wildcard_object_is_a_clean_no_op(self):
        r = self.run_tool(json.dumps(issue(9, "[soundness] something")))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_empty_stdin_is_a_clean_no_op(self):
        r = self.run_tool("")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_non_json_stdin_is_misuse_not_a_silent_pass(self):
        r = self.run_tool("not json at all")
        self.assertEqual(r.returncode, 2)

    def test_a_bare_scalar_is_misuse(self):
        r = self.run_tool("42")
        self.assertEqual(r.returncode, 2)

    def test_emoji_survives_the_round_trip(self):
        # The label contains an emoji and a space; a decode slip turns it into
        # "??" and every labeled proposal then looks unlabeled.
        r = self.run_tool(json.dumps(issue(1, "[wildcard] a")))
        self.assertIn("💎", r.stdout)
        self.assertIn("Bounty", r.stdout)


class RealTemplateTests(unittest.TestCase):
    """The committed form must satisfy the contract the workflow relies on."""

    def setUp(self):
        self.root = os.path.abspath(os.path.join(REAL_TEMPLATE, os.pardir, os.pardir, os.pardir))

    def test_committed_form_declares_the_bounty_routing_labels(self):
        labels = wi.declared_labels(self.root)
        self.assertIn("wildcard", labels)
        self.assertIn("💎 Bounty", labels)

    def test_committed_form_prefix_is_the_bracket_tag(self):
        self.assertTrue(wi.title_prefix(self.root).startswith("[wildcard]"))

    def test_committed_form_round_trips_through_select(self):
        # The end-to-end shape the workflow runs: the real form's own labels,
        # applied to a proposal filed the way an API client files one.
        labels = wi.declared_labels(self.root)
        prefix = wi.title_prefix(self.root)
        sel = wi.select([issue(565, prefix + "Make the Go toolchain the oracle")],
                        labels, prefix)
        self.assertEqual(len(sel), 1)
        self.assertEqual(sorted(sel[0][1]), sorted(labels))


if __name__ == "__main__":
    unittest.main()
