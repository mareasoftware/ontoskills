#!/usr/bin/env bash
# Pre-build opencode into a tarball for fast container injection.
# Run once on the HOST (not in Docker — DNS is often broken inside containers).
# Produces benchmark/opencode_prebuilt.tar.gz (~244 MB).
# Re-run whenever you update the opencode version.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="$SCRIPT_DIR/opencode_prebuilt.tar.gz"

echo "==> Ensuring opencode is installed globally..."
npm install -g opencode-ai@latest 2>&1 | tail -2
OPENDEX_VERSION=$(opencode --version 2>&1 || echo "unknown")
echo "    version: $OPENDEX_VERSION"

NPM_ROOT=$(npm root -g)
echo "    npm root: $NPM_ROOT"

if [ ! -d "$NPM_ROOT/opencode-ai" ]; then
    echo "ERROR: opencode-ai not found at $NPM_ROOT/opencode-ai"
    exit 1
fi

echo "==> Packing opencode as $OUTPUT..."
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

mkdir -p "$TMPDIR/usr/local/lib/node_modules"
cp -r "$NPM_ROOT/opencode-ai" "$TMPDIR/usr/local/lib/node_modules/"
mkdir -p "$TMPDIR/usr/local/bin"
ln -sf ../lib/node_modules/opencode-ai/bin/opencode "$TMPDIR/usr/local/bin/opencode"

tar czf "$OUTPUT" -C "$TMPDIR" usr
rm -rf "$TMPDIR"
trap - EXIT

echo "==> Done: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
