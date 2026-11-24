"""Where things are: the data directory, the metadata directory, the release version.

Three settings, each resolved the same way -- an explicit `configure()` call wins, then an
environment variable, then a default that works both standalone and inside grugrutyp:

| setting   | configure()  | environment        | default                                           |
|-----------|--------------|--------------------|---------------------------------------------------|
| data dir  | `data_dir=`  | `UDCORPUS_DATA`    | `<repo>/data` inside grugrutyp, else `corpus/data` |
| meta dir  | `meta_dir=`  | `UDCORPUS_META`    | `corpus/meta` (shipped with this package)          |
| version   | `version=`   | `UDCORPUS_VERSION` | the highest `treebanks/v*` directory on disk       |

The data directory holds `raw/` (downloaded archives) and `treebanks/v<version>/`
(unpacked UD_* and SUD_* treebank directories side by side); `fetch_treebanks.sh` and
`unpack.sh` use the same rule. Everything is read at call time, never frozen at import,
so a host application (grugrutyp) or a test can `configure()` after importing.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent  # .../corpus

_overrides: dict[str, object] = {}


def configure(
    data_dir: str | Path | None = None,
    meta_dir: str | Path | None = None,
    version: str | None = None,
) -> None:
    """Set any of the three settings for this process. `None` leaves one unchanged."""
    if data_dir is not None:
        _overrides["data_dir"] = Path(data_dir)
    if meta_dir is not None:
        _overrides["meta_dir"] = Path(meta_dir)
    if version is not None:
        _overrides["version"] = str(version)
    # Every cached table depends on these paths.
    from . import languages, treebanks

    languages.reload()
    treebanks.reload()


def reset() -> None:
    """Forget every `configure()` call (tests)."""
    _overrides.clear()
    from . import languages, treebanks

    languages.reload()
    treebanks.reload()


def data_dir() -> Path:
    if "data_dir" in _overrides:
        return _overrides["data_dir"]  # type: ignore[return-value]
    env = os.environ.get("UDCORPUS_DATA")
    if env:
        return Path(env)
    # Inside the grugrutyp repository the data lives beside the code, in <repo>/data.
    if (PACKAGE_ROOT.parent / "backend" / "grugrutyp").is_dir():
        return PACKAGE_ROOT.parent / "data"
    return PACKAGE_ROOT / "data"


def meta_dir() -> Path:
    if "meta_dir" in _overrides:
        return _overrides["meta_dir"]  # type: ignore[return-value]
    env = os.environ.get("UDCORPUS_META")
    return Path(env) if env else PACKAGE_ROOT / "meta"


def treebanks_root(version: str | None = None) -> Path:
    return data_dir() / "treebanks" / f"v{version or default_version()}"


def available_versions() -> list[str]:
    """Release versions unpacked on disk, oldest first (`2.9` before `2.18`)."""
    root = data_dir() / "treebanks"
    if not root.is_dir():
        return []
    found = [p.name[1:] for p in root.iterdir() if p.is_dir() and re.fullmatch(r"v\d+\.\d+", p.name)]
    return sorted(found, key=lambda v: tuple(int(x) for x in v.split(".")))


def default_version() -> str:
    if "version" in _overrides:
        return _overrides["version"]  # type: ignore[return-value]
    env = os.environ.get("UDCORPUS_VERSION")
    if env:
        return env
    versions = available_versions()
    if versions:
        return versions[-1]
    raise FileNotFoundError(
        f"no unpacked release under {data_dir() / 'treebanks'} -- run fetch_treebanks.sh "
        "and unpack.sh, or set UDCORPUS_VERSION / UDCORPUS_DATA"
    )
