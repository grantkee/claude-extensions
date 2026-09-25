#!/usr/bin/env bash
# Build the review scope file for a diff review: the files changed against a
# base ref, plus every file under src/ that imports one of them.
#
# Usage: scope.sh <repo-path> [base-ref]     (base-ref defaults to main)
#
# Writes <repo>/tasks/telx-review/scope.md and prints its path.
set -u

REPO="${1:?usage: scope.sh <repo-path> [base-ref]}"
BASE="${2:-main}"
OUT_DIR="$REPO/tasks/telx-review"
OUT="$OUT_DIR/scope.md"
mkdir -p "$OUT_DIR"
cd "$REPO" || exit 1

BRANCH="$(git branch --show-current 2>/dev/null || echo detached)"
CHANGED="$(git diff --name-only "$BASE"...HEAD 2>/dev/null; git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard -- src 2>/dev/null)"
CHANGED="$(printf '%s\n' "$CHANGED" | grep -v '^$' | sort -u)"

{
  echo "# Review scope"
  echo
  echo "Mode: diff against $BASE"
  echo "Branch: $BRANCH"
  echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## Changed files (committed on the branch, staged, unstaged, and untracked under src/)"
  echo
  if [ -z "$CHANGED" ]; then
    echo "(none)"
  else
    printf '%s\n' "$CHANGED" | sed 's/^/- /'
  fi
  echo
  echo "## Files that import a changed file"
  echo
  found=0
  while IFS= read -r f; do
    case "$f" in src/*.ts|src/*.tsx) ;; *) continue ;; esac
    # src/lib/tokens.ts -> @/lib/tokens ; src/hooks/index.tsx -> @/hooks
    mod="${f#src/}"; mod="${mod%.tsx}"; mod="${mod%.ts}"; mod="${mod%/index}"
    importers="$(grep -rlE "from ['\"]@/${mod}(\.ts|\.tsx|/index)?['\"]" src 2>/dev/null | grep -v -x "$f" | sort)"
    if [ -n "$importers" ]; then
      found=1
      echo "- $f is imported by:"
      printf '%s\n' "$importers" | sed 's/^/  - /'
    fi
  done <<< "$CHANGED"
  [ "$found" = 0 ] && echo "(none found by static import search)"
  echo
  echo "## Diff stat"
  echo
  echo '```'
  git diff --stat "$BASE"...HEAD 2>/dev/null | tail -n 40
  echo '```'
} > "$OUT"

echo "$OUT"
