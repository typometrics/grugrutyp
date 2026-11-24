# grugrutyp backend. Python 3.12+ (3.14 on this box).
#
# Ingestion and language metadata live in the standalone package `udcorpus`, in
# <repo>/corpus/ (corpus/README.md). It is made importable here, relative to this
# checkout, rather than pip-installed: the venv is shared by every checkout (live, worktrees,
# tests), and `pip install -e` would pin it to one of them. Whichever checkout runs,
# its own corpus/ is the one imported.
import sys as _sys
from pathlib import Path as _Path

_CORPUS = _Path(__file__).resolve().parents[2] / "corpus"
if _CORPUS.is_dir() and str(_CORPUS) not in _sys.path:
    _sys.path.insert(0, str(_CORPUS))
