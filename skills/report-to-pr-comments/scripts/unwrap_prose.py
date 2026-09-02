#!/usr/bin/env python3
"""Join hard-wrapped prose into single lines for GitHub comment bodies.

GitHub renders a lone newline inside a comment paragraph as <br>, so a report that was
hard-wrapped at 80 columns turns into a ragged column of short lines. This joins prose
paragraphs while leaving alone the structures that need their own lines: fenced code
blocks, table rows, list items, headings, blockquotes, and horizontal rules.

A wrapped continuation of a list item is joined onto that item's line, which is what you
want -- the item stays one line, it just stops being wrapped.

Usage:
    python3 unwrap_prose.py body.md            # to stdout
    python3 unwrap_prose.py < body.md          # to stdout
    python3 unwrap_prose.py -i body.md         # in place

Caveat: indented (4-space) code blocks are not detected. Use fenced blocks in comment
bodies; the fence is also what GitHub needs for syntax highlighting.
"""

import re
import sys

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
# Table rows, blockquotes, ATX headings, horizontal rules: each keeps its own line.
OWN_LINE = re.compile(r"^\s*(?:\||>|#{1,6}\s|(?:-{3,}|\*{3,}|_{3,})\s*$)")


def unwrap(text: str) -> str:
    out: list[str] = []
    buf: list[str] = []
    in_fence = False
    fence_marker = ""

    def flush() -> None:
        if buf:
            out.append(" ".join(s.strip() for s in buf))
            buf.clear()

    for line in text.split("\n"):
        fence_match = FENCE.match(line)

        if in_fence:
            out.append(line)
            if fence_match and line.strip().startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            continue

        if fence_match:
            flush()
            in_fence = True
            fence_marker = fence_match.group(1)[:3]
            out.append(line)
            continue

        if not line.strip():
            flush()
            out.append("")
            continue

        if OWN_LINE.match(line):
            flush()
            out.append(line.rstrip())
            continue

        if LIST.match(line):
            # Start a new buffer so this item's own wrapped continuations join to it.
            flush()
            buf.append(line.rstrip())
            continue

        buf.append(line)

    flush()
    return "\n".join(out)


def main() -> int:
    args = sys.argv[1:]
    in_place = False
    if args and args[0] in ("-i", "--in-place"):
        in_place = True
        args = args[1:]

    if args:
        path = args[0]
        with open(path, encoding="utf-8") as fh:
            result = unwrap(fh.read())
        if in_place:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(result)
            return 0
    else:
        if in_place:
            print("--in-place needs a file path", file=sys.stderr)
            return 2
        result = unwrap(sys.stdin.read())

    sys.stdout.write(result)
    if not result.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
