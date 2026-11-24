#!/bin/bash
# Moved to corpus/fetch_treebanks.sh (the standalone ingestion package, corpus/README.md).
# Wrapper kept so the release checklist keeps working; all arguments pass through.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/corpus/fetch_treebanks.sh" "$@"
