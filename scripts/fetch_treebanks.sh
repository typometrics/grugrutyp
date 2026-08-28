#!/bin/bash
# Download UD and SUD treebank releases, verify them, and record what was fetched.
#
# The SUD URL is derivable from the version number. The UD one is NOT: LINDAT gives each
# release its own handle, so it has to be passed in and recorded. See docs/data-intake.md.
#
#   ./fetch_treebanks.sh                 # fetch the pinned version
#   ./fetch_treebanks.sh --check         # only report whether a newer release exists
#   ./fetch_treebanks.sh --version 2.19 --ud-handle 11234/1-XXXX
set -euo pipefail

VERSION="2.18"
UD_HANDLE="11234/1-6149"
CHECK_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)   VERSION="$2"; shift 2 ;;
        --ud-handle) UD_HANDLE="$2"; shift 2 ;;
        --check)     CHECK_ONLY=1; shift ;;
        -h|--help)   sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW="$ROOT/data/raw"

SUD_URL="https://grew.fr/download/sud-treebanks-v${VERSION}.tgz"
UD_BASE="https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/handle/${UD_HANDLE}"

check_latest() {
    # Report the highest version advertised on each landing page. Never acts on it:
    # a new UD release changes annotation guidelines, so upgrading invalidates every
    # stored measure. Upgrading is a deliberate act (docs/data-intake.md).
    local sud ud
    sud=$(curl -fsSL https://surfacesyntacticud.org/data/ \
          | grep -oE 'sud-treebanks-v[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' \
          | sort -V | tail -1 || true)
    ud=$(curl -fsSL https://universaldependencies.org/download.html \
          | grep -oE 'ud-treebanks-v[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' \
          | sort -V | tail -1 || true)
    echo "pinned : v$VERSION"
    echo "SUD    : latest advertised v${sud:-unknown}"
    echo "UD     : latest advertised v${ud:-unknown}"
    if [[ -n "$ud" && "$ud" != "$VERSION" ]]; then
        echo
        echo "A newer UD release exists. Find its LINDAT handle on the download page and"
        echo "re-run with:  --version $ud --ud-handle <handle>"
        echo "Import it under a NEW version namespace; do not overwrite v$VERSION."
    fi
}

fetch() {   # fetch <url> <filename>
    local url="$1" out="$RAW/$2"
    echo "==> $2"
    curl -fL --retry 3 --retry-delay 5 -C - -o "$out" "$url"
    if [[ -f "$out.sha256" ]]; then
        (cd "$RAW" && sha256sum -c "$2.sha256") \
            || { echo "CHECKSUM MISMATCH for $2 -- remote changed under a fixed version" >&2; exit 1; }
    else
        (cd "$RAW" && sha256sum "$2" > "$2.sha256")
        echo "    recorded $(cut -c1-16 < "$out.sha256")..."
    fi
}

if [[ $CHECK_ONLY -eq 1 ]]; then check_latest; exit 0; fi

mkdir -p "$RAW"
fetch "$SUD_URL"                             "sud-treebanks-v${VERSION}.tgz"
fetch "$UD_BASE/ud-treebanks-v${VERSION}.tgz" "ud-treebanks-v${VERSION}.tgz"
fetch "$UD_BASE/ud-tools-v${VERSION}.tgz"     "ud-tools-v${VERSION}.tgz"
fetch "$UD_BASE/ud-documentation-v${VERSION}.tgz" "ud-documentation-v${VERSION}.tgz"

cat > "$RAW/SOURCES-v${VERSION}.txt" <<EOF
version    $VERSION
fetched    $(date -Is)
sud_url    $SUD_URL
ud_handle  $UD_HANDLE
ud_base    $UD_BASE
EOF

echo
echo "Done. Next: ./scripts/unpack.sh --version $VERSION"
