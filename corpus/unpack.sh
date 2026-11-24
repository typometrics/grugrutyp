#!/bin/bash
# Unpack the downloaded treebank archives into <data>/treebanks/v<VERSION>/.
#
#   ./unpack.sh [--version 2.19] [--data DIR]
#
# Both archives contain a single top-level directory ({ud,sud}-treebanks-vX.Y), which we
# strip, so UD_* and SUD_* treebank directories end up side by side.
set -euo pipefail

VERSION="2.19"
DATA=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="$2"; shift 2 ;;
        --data)    DATA="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Data directory, same rule as udcorpus/config.py: --data, else $UDCORPUS_DATA, else
# <repo>/data inside grugrutyp, else corpus/data.
if [[ -n "${DATA:-}" ]]; then :
elif [[ -n "${UDCORPUS_DATA:-}" ]]; then DATA="$UDCORPUS_DATA"
elif [[ -d "$HERE/../backend/grugrutyp" ]]; then DATA="$(cd "$HERE/.." && pwd)/data"
else DATA="$HERE/data"
fi
RAW="$DATA/raw"
DEST="$DATA/treebanks/v$VERSION"

mkdir -p "$DEST"
for scheme in sud ud; do
    archive="$RAW/${scheme}-treebanks-v${VERSION}.tgz"
    [[ -f "$archive" ]] || { echo "missing $archive -- run fetch_treebanks.sh first" >&2; exit 1; }
    echo "==> unpacking $(basename "$archive")"
    tar xzf "$archive" -C "$DEST" --strip-components=1
done

echo
echo "$DEST: $(find "$DEST" -maxdepth 1 -name 'UD_*' | wc -l) UD, $(find "$DEST" -maxdepth 1 -name 'SUD_*' | wc -l) SUD treebanks"
