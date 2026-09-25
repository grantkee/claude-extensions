#!/usr/bin/env bash
# Collect build, type-check, lint, and test results for telx-frontend into one
# markdown file that every review agent can read instead of rerunning the tools.
#
# Usage: toolchain.sh <repo-path> [--no-build]
#
# Writes <repo>/tasks/telx-review/toolchain.md and prints its path.
set -u

REPO="${1:?usage: toolchain.sh <repo-path> [--no-build]}"
NO_BUILD="${2:-}"
OUT_DIR="$REPO/tasks/telx-review"
OUT="$OUT_DIR/toolchain.md"
TMP="$(mktemp -d)"
mkdir -p "$OUT_DIR"
cd "$REPO" || exit 1

section() {
  # section <title> <log-file> <exit-code> <tail-lines>
  local title="$1" log="$2" code="$3" lines="$4"
  {
    echo
    echo "## $title"
    echo
    echo "exit code: $code"
    echo
    echo '```'
    tail -n "$lines" "$log"
    echo '```'
  } >> "$OUT"
}

{
  echo "# Toolchain results"
  echo
  echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Branch: $(git branch --show-current 2>/dev/null || echo unknown)"
  echo "Head: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "Node: $(node --version 2>/dev/null || echo missing)"
} > "$OUT"

if [ ! -d node_modules ]; then
  echo >> "$OUT"
  echo "node_modules is missing; run \`npm ci\` before reviewing. No tools were run." >> "$OUT"
  echo "$OUT"
  exit 0
fi

npx tsc --noEmit > "$TMP/tsc.log" 2>&1; section "Type check (npx tsc --noEmit)" "$TMP/tsc.log" $? 40
npm run lint > "$TMP/lint.log" 2>&1;    section "Lint (npm run lint)" "$TMP/lint.log" $? 60
npx jest --ci > "$TMP/jest.log" 2>&1;   section "Tests (npx jest --ci)" "$TMP/jest.log" $? 60

if [ "$NO_BUILD" = "--no-build" ]; then
  printf '\n## Build\n\nSkipped on request.\n' >> "$OUT"
elif lsof -nP -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1; then
  printf '\n## Build\n\nSkipped: something is listening on port 3000 (probably `next dev`), and a concurrent `next build` would corrupt its `.next` directory.\n' >> "$OUT"
elif pgrep -f "next build" >/dev/null 2>&1; then
  printf '\n## Build\n\nSkipped: another `next build` is already running in this checkout. Read its result from that run, or rerun this script once it finishes.\n' >> "$OUT"
else
  # The wagmi config throws without a WalletConnect project id, which breaks
  # prerendering. A placeholder is enough for the build to succeed.
  placeholder_note=""
  if [ -f .env.local ] && grep -q '^NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID=.\+' .env.local; then
    npm run build > "$TMP/build.log" 2>&1; code=$?
  else
    NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID=placeholder npm run build > "$TMP/build.log" 2>&1; code=$?
    placeholder_note="Built with a placeholder WalletConnect project id, so the \`[Reown Config] ... HTTP status code: 403\` lines are expected and not a finding."
  fi
  # Keep the compile status and any errors, but leave the route table to its own section.
  awk '/^Route \(app\)/{exit} {print}' "$TMP/build.log" > "$TMP/build-head.log"
  section "Build (npm run build, includes prebuild security-check)" "$TMP/build-head.log" $code 40
  [ -n "$placeholder_note" ] && printf '\n%s\n' "$placeholder_note" >> "$OUT"
  {
    echo
    echo "### Route table"
    echo
    echo '```'
    awk '/^Route \(app\)/{p=1} p' "$TMP/build.log"
    echo '```'
  } >> "$OUT"
fi

rm -rf "$TMP"
echo "$OUT"
