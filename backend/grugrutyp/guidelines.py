"""Retrieval over the annotation guidelines, for the LLM chat (`nl2grew.chat`/`analyze`).

The chat model knows UD reasonably and SUD barely: it would write `comp:obj` under an
adposition, or a UD-shaped `case` edge in a SUD query. Rather than growing the system
prompt, each chat turn retrieves the few guideline sections closest to what the user
asked and hands them to the model as reference text, with the page names shown back to
the user as sources.

Corpus (`scripts/fetch_guidelines.sh` -> `data/guidelines/`, not committed):

* `pebbles/`  -- the SUD guidelines (pebbles.surfacesyntacticud.org, the reference since
  Oct 2026; documents the 2.19 relabelling of ADP/SCONJ complements to plain `comp`);
* `ud/`       -- UD relation and overview pages (universaldependencies.org);
* `spoken/`   -- UD spoken-language guidelines (grew.fr);
* `sud-rules.md` -- Kim's distilled SUD rules (annotation decisions, known gaps).

Index (`scripts/build_guideline_index.py` -> `data/guidelines/index.json` + `index.npy`):
the pages are cut into heading sections of at most ~1,600 characters and embedded once
with OpenAI `text-embedding-3-small`. A query costs one embedding call (users write in
French as often as in English and the pages are English: embeddings bridge that,
keywords do not). If the embedding call fails, retrieval falls back to BM25 on the same
chunks, and if there is no index at all it returns nothing and the chat works as before.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx

from .meta import DATA_ROOT

GUIDE_DIR = DATA_ROOT / "guidelines"
INDEX_JSON = GUIDE_DIR / "index.json"
INDEX_NPY = GUIDE_DIR / "index.npy"
EMBED_MODEL = "text-embedding-3-small"
OPENAI_BASE = os.environ.get("GRUGRUTYP_LLM_BASE", "https://api.openai.com/v1")
MAX_CHUNK = 1600

# Which collections serve which scheme, and how much a hit from each counts. A SUD user
# still benefits from a UD page where pebbles is silent, but SUD pages should win ties.
SCHEME_WEIGHTS = {
    "SUD": {"pebbles": 1.0, "sud-rules": 1.0, "spoken": 0.85, "ud": 0.75},
    "UD": {"ud": 1.0, "spoken": 0.9, "pebbles": 0.7, "sud-rules": 0.6},
}
COLLECTION_NAMES = {
    "pebbles": "SUD guidelines",
    "ud": "UD guidelines",
    "spoken": "UD spoken guidelines",
    "sud-rules": "SUD rules (Kim Gerdes)",
}


@dataclass
class Chunk:
    collection: str
    title: str
    url: str
    text: str


# --------------------------------------------------------------------------- chunking


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end > 0:
            for line in text[4:end].splitlines():
                if ":" in line and not line.startswith(" "):
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip().strip("'\"")
            text = text[end + 4:]
    match = re.match(r"\s*<!-- source: (\S+)", text)
    if match:
        meta.setdefault("source", match.group(1))
    return meta, text


def _collection(path: Path) -> str:
    rel = path.relative_to(GUIDE_DIR)
    return "sud-rules" if rel.name == "sud-rules.md" else rel.parts[0]


def _url(path: Path, meta: dict[str, str]) -> str:
    if meta.get("source"):
        return meta["source"]
    rel = path.relative_to(GUIDE_DIR)
    if rel.parts[0] == "pebbles":
        slug = "/".join(rel.parts[1:])[: -len(".md")]
        slug = slug[: -len("/index")] if slug.endswith("/index") else slug
        return f"https://pebbles.surfacesyntacticud.org/guidelines/{slug}"
    return ""


def _clean(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<div[^>]*>.*?</div>", "", text, flags=re.S)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_file(path: Path) -> list[Chunk]:
    meta, body = _frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    body = _clean(body)
    if len(body) < 80:
        return []
    collection = _collection(path)
    first_heading = re.search(r"^#\s+(.+)$", body, flags=re.M)
    title = meta.get("title") or (first_heading.group(1) if first_heading else "")
    if collection == "ud" and path.stem.startswith(("u_dep_", "u_feat_")):
        # u_dep_acl-relcl -> "acl:relcl"; u_feat_Foreign -> "Foreign (feature)"
        name = path.stem.split("_", 2)[2]
        title = name.replace("-", ":") if path.stem.startswith("u_dep_") else f"{name} (feature)"
    title = (title or path.stem).strip("` ")
    url = _url(path, meta)
    if meta.get("request"):
        body = f"Grew request: {meta['request']}\n\n{body}"

    # Split at ## / ### headings; keep the page title in front of every piece so a
    # section read alone still says what it is about.
    sections = re.split(r"(?m)^(?=#{2,3} )", body)
    chunks: list[Chunk] = []
    buffer = ""
    for section in sections:
        if buffer and len(buffer) + len(section) > MAX_CHUNK:
            chunks.append(Chunk(collection, title, url, buffer.strip()))
            buffer = ""
        buffer += section
        while len(buffer) > MAX_CHUNK:
            cut = buffer.rfind("\n", 0, MAX_CHUNK)
            cut = cut if cut > MAX_CHUNK // 2 else MAX_CHUNK
            chunks.append(Chunk(collection, title, url, buffer[:cut].strip()))
            buffer = buffer[cut:]
    if buffer.strip():
        chunks.append(Chunk(collection, title, url, buffer.strip()))
    for chunk in chunks:
        chunk.text = f"[{COLLECTION_NAMES[collection]} — {title}]\n{chunk.text}"
    return chunks


def all_chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(GUIDE_DIR.rglob("*.md")):
        if path.name == "README.md":
            continue
        chunks.extend(chunk_file(path))
    return chunks


# --------------------------------------------------------------------------- embeddings


def embed(texts: list[str], timeout: float = 20.0) -> list[list[float]]:
    response = httpx.post(
        f"{OPENAI_BASE}/embeddings",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": EMBED_MODEL, "input": texts},
        timeout=timeout,
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


# --------------------------------------------------------------------------- index


def _index():
    """(chunks, unit-normalised matrix or None, bm25). None when nothing is built.

    Keyed on the index file's mtime: `scripts/update_guidelines.sh` rewrites it and the
    running API picks the new index up on the next chat turn -- no restart."""
    try:
        mtime = INDEX_JSON.stat().st_mtime
    except FileNotFoundError:
        return None
    return _load_index(mtime)


@lru_cache(maxsize=1)
def _load_index(mtime: float):
    import numpy as np

    chunks = [Chunk(**c) for c in json.loads(INDEX_JSON.read_text(encoding="utf-8"))]
    matrix = None
    if INDEX_NPY.exists():
        matrix = np.load(INDEX_NPY).astype("float32")
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
        if matrix.shape[0] != len(chunks):
            matrix = None
    return chunks, matrix, _Bm25([c.text for c in chunks])


def reload() -> None:
    _load_index.cache_clear()


_TOKEN = re.compile(r"[\w@]+(?::[\w@]+)*", re.U)
_STOP = frozenset(
    "the a an of to in and or is are be for on with as by that this it its from at which "
    "le la les de des du un une et ou est sont pour sur avec par que qui dans en au aux "
    "je veux voudrais comment combien mesurer".split()
)


def _tokens(text: str) -> list[str]:
    out = []
    for token in _TOKEN.findall(text.lower()):
        if token in _STOP or len(token) < 2:
            continue
        out.append(token)
        if ":" in token:  # comp:obj also counts as comp and obj
            out.extend(part for part in token.split(":") if part)
    return out


class _Bm25:
    def __init__(self, docs: list[str], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(_tokens(d)) for d in docs]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / max(len(self.docs), 1)
        df: Counter = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = _tokens(query)
        out = []
        for doc, length in zip(self.docs, self.lengths):
            score = 0.0
            for t in terms:
                f = doc.get(t)
                if f:
                    score += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * length / self.avg)
                    )
            out.append(score)
        return out


# French (and a little German) linguistic vocabulary -> the English terms and labels the
# guidelines use. Appended to the query, never replacing it: embeddings handle most of
# the cross-language gap, this pins the technical terms that they blur.
GLOSSARY = {
    "complétive": "complement clause clausal complement ccomp comp:obj SCONJ",
    "subordonn": "subordinate clause subordinating conjunction SCONJ mark",
    "relative": "relative clause relcl mod@relcl acl:relcl",
    "préposition": "adposition ADP comp complement of adposition case",
    "postposition": "adposition ADP comp complement of adposition case",
    "adposition": "adposition ADP comp complement of adposition case",
    "objet": "object comp:obj obj",
    "sujet": "subject subj nsubj",
    "auxiliaire": "auxiliary AUX comp:aux aux",
    "copule": "copula comp:pred cop",
    "déterminant": "determiner DET det",
    "adjectif": "adjective ADJ mod amod",
    "adverbe": "adverb ADV mod advmod",
    "coordination": "coordination conj cc conj:coord",
    "conjonction": "conjunction CCONJ SCONJ cc mark",
    "infinitive": "infinitive VerbForm=Inf",
    "passif": "passive voice Voice=Pass subj@pass @agent",
    "agent": "passive agent @agent obl:agent",
    "clitique": "clitic pronoun PRON",
    "pronom": "pronoun PRON",
    "nom propre": "proper noun PROPN",
    "numéral": "numeral NUM nummod det:num",
    "classificateur": "classifier clf mod:clf",
    "possessi": "possessive Poss mod:poss nmod:poss",
    "dislo": "dislocated dislocation",
    "parenth": "parataxis parenthetical parataxis:parenth",
    "discours": "discourse marker discourse",
    "racine": "root",
    "ordre des mots": "word order",
    "prédicat": "predicate",
    "attribut": "predicative complement comp:pred xcomp",
}
_LANGUAGE_WORDS = {
    "fr": ("french", "français", "francais"),
    "zh": ("chinese", "chinois", "mandarin"),
    "pcm": ("naija", "pidgin"),
    "ha": ("hausa", "haoussa"),
    "say": ("zaar", "saya"),
    "fsl": ("french sign", "lsf", "langue des signes"),
}


def expand_query(query: str) -> str:
    low = query.lower()
    extra = [terms for key, terms in GLOSSARY.items() if key in low]
    return f"{query}\n{' '.join(extra)}" if extra else query


def _page_weight(chunk: Chunk, query_low: str) -> float:
    """Language-specific pebbles pages answer questions about that language; for any
    other question they are noise that a French-language query pulls in by sheer
    lexical similarity."""
    match = re.search(r"/language_specific/([^/]+)/", chunk.url)
    if not match:
        return 1.0
    words = _LANGUAGE_WORDS.get(match.group(1), (match.group(1),))
    return 1.0 if any(w in query_low for w in words) else 0.6


def retrieve(query: str, scheme: str = "SUD", k: int = 5) -> list[Chunk]:
    """The k guideline sections closest to `query`, weighted for the scheme; [] if no
    index is built. Never raises: retrieval is an aid, the chat must work without it."""
    try:
        index = _index()
    except Exception:  # noqa: BLE001
        return []
    if index is None or not query.strip():
        return []
    chunks, matrix, bm25 = index
    weights = SCHEME_WEIGHTS.get(scheme.upper(), SCHEME_WEIGHTS["SUD"])
    expanded = expand_query(query)
    query_low = query.lower()

    # Keywords, scaled to [0, 1]; then, when the embedding call works, a hybrid in
    # which the embedding carries most of the weight and the keywords pin exact labels.
    keyword = bm25.scores(expanded)
    top = max(keyword) or 1.0
    scores = [x / top for x in keyword]
    if matrix is not None and os.environ.get("OPENAI_API_KEY"):
        try:
            import numpy as np

            vector = np.asarray(embed([expanded[:4000]], timeout=8.0)[0], dtype="float32")
            vector /= np.linalg.norm(vector) + 1e-9
            cosine = (matrix @ vector).tolist()
            scores = [0.75 * c + 0.25 * 0.6 * kw for c, kw in zip(cosine, scores)]
        except Exception:  # noqa: BLE001 -- keywords alone
            pass
    final = [
        scores[i] * weights.get(chunks[i].collection, 0.5) * _page_weight(chunks[i], query_low)
        for i in range(len(chunks))
    ]
    ranked = sorted(range(len(chunks)), key=final.__getitem__, reverse=True)
    picked: list[Chunk] = []
    seen_pages: set[str] = set()
    for i in ranked:
        if final[i] <= 0:
            break
        chunk = chunks[i]
        page = chunk.url or chunk.title
        if page in seen_pages:  # one section per page: breadth over depth
            continue
        seen_pages.add(page)
        picked.append(chunk)
        if len(picked) == k:
            break
    return picked


def context_message(chunks: list[Chunk]) -> str:
    """The system message the chat receives: the excerpts, and how to use them."""
    parts = [
        "GUIDELINE EXCERPTS retrieved for this question (annotation guidelines of the "
        "scheme; may be partial). Use them to get the scheme's analysis and relation "
        "names right. When they conflict with your general knowledge, the excerpts win; "
        "when they conflict with the TRAPS/SCHEME rules above about the data actually "
        "loaded (UD/SUD 2.19), those rules win. Mention a guideline page by name when "
        "your reply relies on it."
    ]
    parts += [chunk.text for chunk in chunks]
    return "\n\n---\n\n".join(parts)


def sources(chunks: list[Chunk]) -> list[dict]:
    seen: dict[str, dict] = {}
    for chunk in chunks:
        key = f"{chunk.collection}:{chunk.title}"
        seen.setdefault(key, {
            "title": chunk.title,
            "collection": COLLECTION_NAMES[chunk.collection],
            "url": chunk.url,
        })
    return list(seen.values())
