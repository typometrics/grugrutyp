#!/bin/bash
# Fetch the annotation guidelines the LLM chat retrieves from (backend/grugrutyp/guidelines.py).
#
#   scripts/fetch_guidelines.sh            # then: .venv/bin/python scripts/build_guideline_index.py
#
# * SUD: pebbles (https://pebbles.surfacesyntacticud.org/), the reference since 23 Oct 2026,
#   from its GitHub source, content/guidelines/. It documents the 2.19 relabelling (ADP/SCONJ
#   complements are plain `comp`); the older guidelines.surfacesyntacticud.org does not.
# * UD + UD spoken guidelines + Kim's SUD pre-annotation rules: the local copies kept on calcul
#   in sawmill/general (fetched there from universaldependencies.org and grew.fr, Sept 2026).
#
# The text is not committed (third-party licences); data/guidelines/ is gitignored.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=data/guidelines
PEBBLES_REF=${PEBBLES_REF:-main}
CALCUL=${CALCUL:-gerdes@calcul-kimgerdes.lisn.upsaclay.fr:/bigstorage/kim/sawmill/general}

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
git clone -q --depth 1 --branch "$PEBBLES_REF" https://github.com/surfacesyntacticud/pebbles.git "$tmp/pebbles"
rm -rf "$DEST/sud" "$DEST/pebbles"
mkdir -p "$DEST/pebbles"
cp -r "$tmp/pebbles/content/guidelines/." "$DEST/pebbles/"
echo "pebbles $(git -C "$tmp/pebbles" log -1 --format='%H %ci')" > "$DEST/SOURCES"

rsync -a --delete "$CALCUL/guidelines/ud/" "$DEST/ud/"
rsync -a --delete "$CALCUL/guidelines/spoken/" "$DEST/spoken/"
rsync -a "$CALCUL/sud-rules.md" "$DEST/sud-rules.md"
echo "ud, spoken, sud-rules.md from $CALCUL ($(date -u +%F))" >> "$DEST/SOURCES"
find "$DEST" -name '*.md' | wc -l | xargs echo "markdown pages:"
