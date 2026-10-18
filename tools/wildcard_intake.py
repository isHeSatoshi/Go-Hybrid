#!/usr/bin/env python3
"""wildcard_intake.py — the Wildcard Track's intake labels, from one source.

BOUNTY.md Track 3 runs a separate $500/cycle pool for wildcard proposals,
and MOONSHOT.md is its ledger. `.github/ISSUE_TEMPLATE/wildcard.yml` declares
the routing labels:

    title: "[wildcard] "
    labels: ["wildcard", "💎 Bounty"]

GitHub applies those labels **only** when the issue is created through the
web template chooser. A template-shaped body filed through the API
(`gh issue create --body-file`, which is how an agent or a script files an
issue) skips the frontmatter entirely and lands with no labels at all.

That is not a cosmetic difference. Measured on 2026-10-18 against
MOONSHOT.md's ledger:

    labeled   + in ledger    : 10
    labeled   + not in ledger:  5
    unlabeled + in ledger    :  0
    unlabeled + not in ledger: 12

Not one unlabeled proposal has ever reached the ledger, and several
unlabeled ones are OLDER than labeled proposals that did. The label is the
routing key into triage, so the filing path silently decided eligibility.

This module is the single source of truth for both halves of the fix:

  * `declared_labels()` / `title_prefix()` read the template, so the
    workflow never hardcodes a label and cannot drift from the form.
  * `needs_labels()` is the selection predicate, kept pure and unit-tested
    so the backfill and the on-open job share one implementation.

`--select` accepts either a JSON list (`gh issue list`) or a single issue
object (`gh issue view`), because the two workflow jobs read those two
different shapes. Accepting both keeps one tested code path rather than a
second, untested one written in YAML.

Stdlib only. Exit codes: 0 = ok, 1 = problem found, 2 = misuse.
"""
import argparse
import json
import os
import re
import sys

TEMPLATE_REL = os.path.join(".github", "ISSUE_TEMPLATE", "wildcard.yml")


class TemplateError(Exception):
    """The wildcard issue form is missing or malformed."""


def read_template(root="."):
    """Return the wildcard form's frontmatter as a dict.

    Only the handful of scalar/list keys this module needs are parsed, so
    there is no YAML dependency. The form is the source of truth; a missing
    or unreadable file is an error rather than a silent skip, because the
    whole point is that the labels cannot be guessed.
    """
    path = os.path.join(root, TEMPLATE_REL)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise TemplateError(f"cannot read {TEMPLATE_REL}: {e}") from e

    # Frontmatter ends at the first top-level key after the header block;
    # for an issue form that is `body:`.
    front = {}
    for line in lines:
        if line.startswith("body:"):
            break
        if not line or line[0] in " \t#":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        front[key.strip()] = value.strip()

    if "labels" not in front:
        raise TemplateError(f"{TEMPLATE_REL} declares no `labels:` key")
    try:
        labels = json.loads(front["labels"])
    except ValueError as e:
        raise TemplateError(
            f"{TEMPLATE_REL} `labels:` is not a JSON list: {front['labels']!r}"
        ) from e
    if not isinstance(labels, list) or not labels:
        raise TemplateError(f"{TEMPLATE_REL} `labels:` must be a non-empty list")
    if not all(isinstance(x, str) and x.strip() for x in labels):
        raise TemplateError(f"{TEMPLATE_REL} `labels:` has a non-string entry")

    title = front.get("title", "")
    if title:
        try:
            title = json.loads(title)
        except ValueError:
            # An unquoted YAML scalar is legal too; take it verbatim.
            title = title.strip().strip("'\"")
    front["labels"] = labels
    front["title"] = title
    return front


def declared_labels(root="."):
    """The labels the wildcard form declares, in declaration order."""
    return list(read_template(root)["labels"])


def title_prefix(root="."):
    """The title prefix the wildcard form prepends (e.g. `[wildcard] `)."""
    return read_template(root)["title"]


def needs_labels(issue, labels, prefix):
    """Does `issue` need any of `labels` applied?

    `issue` is one element of `gh issue list --json number,title,labels`.
    A non-wildcard title is out of scope: the form is what declares these
    labels, and a title that does not carry the form's prefix was not filed
    as a wildcard proposal, so labelling it would misroute triage.

    A PR is never a proposal. `gh issue list` can return pull requests, so
    the `pull_request` key is checked rather than assumed absent.
    """
    if issue.get("pull_request"):
        return False
    title = issue.get("title") or ""
    if prefix and not title.startswith(prefix):
        return False
    have = {lb.get("name") for lb in (issue.get("labels") or [])}
    return any(want not in have for want in labels)


def missing_labels(issue, labels):
    """The subset of `labels` this issue does not yet carry."""
    have = {lb.get("name") for lb in (issue.get("labels") or [])}
    return [want for want in labels if want not in have]


def select(issues, labels, prefix):
    """The (number, missing) pairs for every issue that needs labelling."""
    out = []
    for it in issues:
        if needs_labels(it, labels, prefix):
            out.append((it["number"], missing_labels(it, labels)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repo root (default: cwd)")
    ap.add_argument(
        "--select",
        action="store_true",
        help="read `gh issue list --json number,title,labels` on stdin and "
             "print one `number:label,label` line per issue needing labels",
    )
    ap.add_argument(
        "--print-labels",
        action="store_true",
        help="print the form's declared labels, one per line",
    )
    ap.add_argument(
        "--print-prefix",
        action="store_true",
        help="print the form's title prefix",
    )
    args = ap.parse_args()

    try:
        labels = declared_labels(args.root)
        prefix = title_prefix(args.root)
    except TemplateError as e:
        print(f"usage error: {e}", file=sys.stderr)
        return 2

    if args.print_labels:
        for lb in labels:
            print(lb)
        return 0
    if args.print_prefix:
        print(prefix)
        return 0

    if args.select:
        raw = sys.stdin.read()
        try:
            data = json.loads(raw) if raw.strip() else []
        except ValueError as e:
            print(f"usage error: stdin is not JSON: {e}", file=sys.stderr)
            return 2
        # The two callers read different gh shapes: `gh issue list` returns a
        # list, `gh issue view` returns one object. Accepting both here keeps
        # one tested code path instead of a second, untested one in YAML.
        if isinstance(data, dict):
            issues = [data]
        elif isinstance(data, list):
            issues = data
        else:
            print(
                "usage error: stdin JSON must be an issue object or a list of them",
                file=sys.stderr,
            )
            return 2
        for number, missing in select(issues, labels, prefix):
            print(f"{number}:{','.join(missing)}")
        return 0

    # No action selected: report the wiring so a human can eyeball it.
    print(f"wildcard form labels : {', '.join(labels)}")
    print(f"wildcard title prefix: {prefix!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
