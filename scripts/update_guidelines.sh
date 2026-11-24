#!/bin/bash
# Update the chat's guidelines in one go: fetch, and re-embed only if a page changed.
#
#   scripts/update_guidelines.sh          # by hand, any time the SUD/UD guidelines changed
#   scripts/update_guidelines.sh --force  # re-embed even if nothing changed
#
# Also runs weekly from /etc/cron.d/grugrutyp-guidelines. The running API picks the new
# index up by itself (it watches index.json); no restart. Cost of a re-embed: < 1 cent.
# Log: /var/log/grugrutyp-guidelines.log when run from cron.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=data/guidelines
hash_pages() { find "$DEST" -name '*.md' -type f -print0 2>/dev/null | sort -z | xargs -0 cat 2>/dev/null | sha256sum | cut -c1-16; }

echo "== $(date -u '+%F %T') update_guidelines"
before_src=$(head -1 "$DEST/SOURCES" 2>/dev/null || echo none)
scripts/fetch_guidelines.sh
after_src=$(head -1 "$DEST/SOURCES")
now=$(hash_pages)
last=$(cat "$DEST/.pages.sha" 2>/dev/null || echo none)
echo "pebbles: ${before_src#pebbles } -> ${after_src#pebbles }"

if [ "$now" = "$last" ] && [ "${1:-}" != "--force" ] && [ -f "$DEST/index.npy" ]; then
  echo "no page changed; index kept"
  exit 0
fi
.venv/bin/python scripts/build_guideline_index.py
echo "$now" > "$DEST/.pages.sha"
echo "index rebuilt; the API reloads it on the next chat turn"
