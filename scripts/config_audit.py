#!/usr/bin/env python3
"""Moved: the language-configuration audit is `python -m udcorpus.audit` (corpus/).

Kept as a wrapper so the release checklist and muscle memory keep working:

    .venv/bin/python scripts/config_audit.py [--json] [--backfill-lcodes] ...

It audits grugrutyp's live release (`.env` GRUGRUTYP_VERSION) against corpus/meta/.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from grugrutyp import meta  # noqa: E402,F401 -- configures udcorpus: data root, live release
from udcorpus.audit import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
