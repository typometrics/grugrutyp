#!/bin/bash
# Unpack the downloaded treebank archives into data/treebanks/v<VERSION>/.
#
# Both archives contain a single top-level directory ({ud,sud}-treebanks-vX.Y), which we
# strip, so UD_* and SUD_* treebank directories end up side by side.
set -euo pipefail

VERSION="2.18"
[[ "${1:-}" == "--version" ]] && VERSION="$2"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW="$ROOT/data/raw"
DEST="$ROOT/data/treebanks/v$VERSION"

mkdir -p "$DEST"
for scheme in sud ud; do
    archive="$RAW/${scheme}-treebanks-v${VERSION}.tgz"
    [[ -f "$archive" ]] || { echo "missing $archive -- run fetch_treebanks.sh first" >&2; exit 1; }
    echo "==> unpacking $(basename "$archive")"
    tar xzf "$archive" -C "$DEST" --strip-components=1
done

echo
echo "$DEST: $(find "$DEST" -maxdepth 1 -name 'UD_*' | wc -l) UD, $(find "$DEST" -maxdepth 1 -name 'SUD_*' | wc -l) SUD treebanks"
