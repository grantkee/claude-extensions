#!/usr/bin/env python3
"""Anchor helper for GitHub pull request review comments.

Three jobs:

  lines   List every commentable line of a PR's diff, per file. Additions and context
          lines are both commentable; anything else is not.

  check   Answer "can I anchor a comment at PATH:LINE?" and, when the answer is no,
          name the nearest lines that are in the diff.

  verify  Map a pending review's comment positions back to file line numbers. Pending
          comments come back with line: null and a diff position, so this is the only
          way to see where they actually landed.

Position semantics, which is where this usually goes wrong: split the file's patch on
newlines and index 0 is the first "@@" header. `position` indexes directly into that
list, so position 1 is the line immediately after the first header. Later "@@" headers
and "-" deletion lines each consume a position but map to no new-file line. Skipping
those produces a consistent off-by-N that makes every anchor look misplaced.

Usage:
    python3 diff_anchors.py lines  OWNER/REPO PR [PATH ...]
    python3 diff_anchors.py check  OWNER/REPO PR PATH LINE
    python3 diff_anchors.py verify OWNER/REPO PR REVIEW_ID

Requires the gh CLI, authenticated.
"""

import json
import re
import subprocess
import sys

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def gh_json(endpoint):
    """Call `gh api --paginate` and return a flat list, tolerating concatenated pages."""
    proc = subprocess.run(
        ["gh", "api", "--paginate", endpoint],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"gh api {endpoint} failed:\n{proc.stderr.strip()}")

    decoder = json.JSONDecoder()
    text, idx, items = proc.stdout, 0, []
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        obj, idx = decoder.raw_decode(text, idx)
        items.extend(obj) if isinstance(obj, list) else items.append(obj)
    return items


def walk_patch(patch):
    """Yield (position, new_file_line_or_None, kind, text) for every line of a patch.

    kind is one of: hunk, add, ctx, del, meta. position equals the line's index in the
    patch, which is exactly GitHub's diff position.
    """
    new_line = 0
    for position, raw in enumerate(patch.split("\n")):
        match = HUNK.match(raw)
        if match:
            new_line = int(match.group(1)) - 1
            yield position, None, "hunk", raw
        elif raw.startswith("-"):
            yield position, None, "del", raw
        elif raw.startswith("\\"):  # "\ No newline at end of file"
            yield position, None, "meta", raw
        else:
            new_line += 1
            yield position, new_line, "add" if raw.startswith("+") else "ctx", raw


def line_index(patch):
    """new-file line number -> (position, kind)."""
    return {
        line: (position, kind)
        for position, line, kind, _ in walk_patch(patch)
        if line is not None
    }


def position_to_line(patch, position):
    """Diff position -> new-file line number, or None if the position has no line."""
    if position is None:
        return None
    for pos, line, _, _ in walk_patch(patch):
        if pos == position:
            return line
    return None


def pr_files(repo, pr):
    files = gh_json(f"repos/{repo}/pulls/{pr}/files")
    return {f["filename"]: f.get("patch") for f in files}


def as_ranges(numbers):
    numbers = sorted(numbers)
    out, start, prev = [], None, None
    for n in numbers:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append((start, prev))
            start = prev = n
    if start is not None:
        out.append((start, prev))
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in out)


def cmd_lines(repo, pr, paths):
    for path, patch in pr_files(repo, pr).items():
        if paths and path not in paths:
            continue
        if not patch:
            print(f"{path}\n  no patch (binary, too large, or rename only) -- cannot anchor inline\n")
            continue
        index = line_index(patch)
        adds = [ln for ln, (_, kind) in index.items() if kind == "add"]
        ctxs = [ln for ln, (_, kind) in index.items() if kind == "ctx"]
        print(path)
        print(f"  added   {as_ranges(adds) or '(none)'}")
        print(f"  context {as_ranges(ctxs) or '(none)'}\n")


def cmd_check(repo, pr, path, line):
    patch = pr_files(repo, pr).get(path)
    if patch is None:
        sys.exit(f"{path} is not in this PR's changed files")
    if not patch:
        sys.exit(f"{path} has no patch (binary, too large, or rename only) -- cannot anchor inline")

    index = line_index(patch)
    if line in index:
        position, kind = index[line]
        label = "an added line" if kind == "add" else "a context line"
        print(f"IN DIFF  {path}:{line} is {label} (position {position}, side RIGHT)")
        if kind == "ctx":
            near_add = min(
                (ln for ln, (_, k) in index.items() if k == "add"),
                key=lambda ln: (abs(ln - line), ln),
                default=None,
            )
            if near_add is not None:
                print(f"         nearest added line: {near_add} -- prefer it if it is the same code")
        return

    print(f"OFF DIFF {path}:{line} is not in a hunk. Name this line in the comment body.")
    for kind, label in (("add", "added"), ("ctx", "context")):
        candidates = sorted(
            (ln for ln, (_, k) in index.items() if k == kind),
            key=lambda ln: (abs(ln - line), ln),
        )[:5]
        if candidates:
            print(f"  nearest {label} lines: {', '.join(map(str, candidates))}")
    print("  pick the one that is topically right, not the numerically closest")


def cmd_verify(repo, pr, review_id):
    patches = pr_files(repo, pr)
    comments = gh_json(f"repos/{repo}/pulls/{pr}/reviews/{review_id}/comments")
    if not comments:
        print("no comments on that review")
        return
    for c in comments:
        path = c.get("path", "?")
        position = c.get("position")
        patch = patches.get(path)
        if position is None:
            where = "OUTDATED (position null -- the anchored code moved or went away)"
        elif patch is None:
            where = f"position {position} (file not in current diff)"
        else:
            line = position_to_line(patch, position)
            where = f"{path}:{line}" if line else f"position {position} maps to no new-file line"
        first = (c.get("body") or "").strip().split("\n", 1)[0]
        print(f"{where}\n    {first[:120]}\n")


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "lines":
            cmd_lines(rest[0], rest[1], set(rest[2:]))
        elif cmd == "check":
            cmd_check(rest[0], rest[1], rest[2], int(rest[3]))
        elif cmd == "verify":
            cmd_verify(rest[0], rest[1], rest[2])
        else:
            sys.exit(__doc__)
    except IndexError:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
