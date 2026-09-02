"""Plain language into a Grew query pair. Phase 6.5.

The one feature that spends money per use, so it is triple-gated: a signed-in account,
the `llm_allowed` flag an admin set by hand, and a per-user daily quota. And it is
honest by construction: nothing the model writes is trusted -- every candidate goes
through the same `MeasureSpec.validate()` as a hand-typed query, an invalid one is sent
back to the model once with the validator's own error, and what the user receives is a
*proposal in the editors*, previewed exactly like anything they type. The fan-out over
705 treebanks still only happens when they press Plot.

Model choice is empirical, not aesthetic: `scripts/nl2grew_bench.py` feeds every preset's
description to a candidate model and checks the result two ways -- does it compile, and
does it return the **same counts** as the reference query on a real treebank. The
default in `GRUGRUTYP_LLM_MODEL` is whatever won that benchmark; see `docs/nl2grew.md`.
"""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache

import httpx

from .engine.neo4j_engine import load_env
from .measure import MeasureSpec

load_env()


@lru_cache(maxsize=1)
def _known_features() -> frozenset[str] | None:
    """Every property key the corpus has ever stored, or None when Neo4j is out of
    reach (unit tests, cold deploys) — the check is then skipped, never fataled."""
    try:
        from .engine.neo4j_engine import get_engine

        return frozenset(get_engine().feature_keys())
    except Exception:  # noqa: BLE001
        return None


def _check_features(spec: MeasureSpec) -> None:
    """Reject feature names no treebank has ever carried.

    The validator is structural and database-free by design, so an invented feature
    (`S.depth = 2`) passes it — and a query testing a property that exists nowhere is
    not an error at run time, it is a plausible-looking measure that is zero for every
    language. Model output goes through this extra gate; the error goes back to the
    model like any validation failure."""
    known = _known_features()
    if known is None:
        return
    unknown = sorted(spec.feature_names() - known)
    if unknown:
        plural = "s" if len(unknown) > 1 else ""
        raise ValueError(
            f"unknown feature{plural} {', '.join(unknown)}: no treebank has "
            f"{'them' if plural else 'it'}. Use real morphology (upos, lemma, Number, "
            "Case, …) or the stored counters subtree_size / n_children / n_left / "
            "n_right; never invent feature names."
        )

OPENAI_BASE = os.environ.get("GRUGRUTYP_LLM_BASE", "https://api.openai.com/v1")
DEFAULT_MODEL = os.environ.get("GRUGRUTYP_LLM_MODEL", "gpt-5.4-mini")
DAILY_QUOTA = int(os.environ.get("GRUGRUTYP_LLM_DAILY", "50"))
TIMEOUT = 90.0

# One retry with the validator's error: measured in the benchmark as worth several
# points of accuracy, while a second retry only ever rescued garbage into different
# garbage.
MAX_ATTEMPTS = 2


def configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


# ----------------------------------------------------------------- the Grew knowledge
#
# Everything the model needs and nothing it can abuse: the request syntax that
# translate/validate actually supports, the scope/response contract, the scheme
# differences that silently flip a measure's meaning, and the root-node trap. Distilled
# from docs/grew-query-language.md, docs/query-pairs.md and docs/measures-mapping.md --
# when those change, this must change with them.

SYSTEM_PROMPT = """You translate a linguist's plain-language description of a typological measure into a Grew query pair for one annotation scheme (SUD or UD, given in the request).

A measure is:
- kind "ratio": a scope S (what to count) and a response Q (which of those also do something). The plotted value is 100 * #(S AND Q) / #(S).
- kind "aggregate": a scope S and a numeric expression aggregated over its matchings (no response).

Output STRICT JSON, nothing else:
{"kind": "ratio" | "aggregate",
 "scope": "<Grew request with a pattern block>",
 "response": "<with/without blocks only, empty string if kind=aggregate>",
 "expression": "<aggregate only, else empty>",
 "aggregation": "avg" | "sum" | "min" | "max",
 "label": "<short axis caption, a few words>",
 "explanation": "<one sentence: what will be measured, in the user's language>"}

GREW SYNTAX YOU MAY USE
- scope: pattern { ... } plus optional with { } / without { } blocks.
- response: ONLY with { } / without { } blocks, and they may ONLY use node names the scope binds. Never a pattern block in the response.
- nodes: X [upos=NOUN], X [upos=NOUN|PROPN], X [Number=Plur], X [upos=*] (any word), X [form="__0__"].
- edges: GOV -[label]-> DEP. In SUD, labels are feature structures: -[1=subj]->, -[1=comp,2=obj]->, -[1=mod]->. In UD, plain labels: -[nsubj]->, -[obj]->, -[amod]->, -[case]->; a bare label like -[1=aux]-> subsumes subtypes in both schemes. Unlabelled: GOV -> DEP.
- order: with { GOV << DEP } (GOV anywhere before DEP), X < Y (immediately before).
- sentence-level: response can be global { is_projective } (or is_tree, is_not_projective).
- aggregate expressions: delta(GOV, DEP) (signed position difference DEP-GOV), abs(delta(GOV, DEP)), length(GOV, DEP), X.subtree_size, X.n_children, sentence.height, sentence.length.
- numeric counters as constraints: every word carries subtree_size (itself plus all its descendants, so a word spanning exactly two tokens has subtree_size 2), n_children, n_left, n_right, and they can be tested with = in any block: with { S.subtree_size = 2 }. These four are the ONLY computed node features that exist. Everything else must be real treebank morphology (upos, xpos, lemma, form, Number, Case, Tense, …) — NEVER invent a feature name (there is no depth, weight, span, size, length or n_tokens feature).

SCHEME DIFFERENCES THAT CHANGE MEANING
- subject: SUD -[1=subj]->, UD -[1=nsubj]->. direct object: SUD -[1=comp,2=obj]->, UD -[1=obj]->. adjectival modifier: SUD -[1=mod]-> with DEP [upos=ADJ], UD -[1=amod]->.
- ALWAYS write the relation in feature form (-[1=nsubj]->, -[1=case]->) in BOTH schemes: the 1= form subsumes subtypes (nsubj:pass, nsubj:outer, aux:caus…), which is almost always what a typological measure means. A plain -[nsubj]-> matches only the exact label — use it only when the user explicitly excludes subtypes.
- subsumption caveats — subtypes that change the meaning, not just the coverage: 1=obl also matches passive agents (obl:agent); 1=aux also matches causative markers (aux:caus); 1=acl folds relative clauses into all adnominal clauses; and nsubj:outer attaches the outer subject to the INNER predicate's head, so same-governor patterns pair it with the wrong clause. When the description targets or excludes such a subclass, restrict the subtype explicitly (-[1=acl,2=relcl]->) or exclude it with a without block — do not rely on bare 1=.
- adpositions: SUD makes the adposition the governor of the noun (A -> N with A [upos=ADP]); UD makes it a case dependent (N -[1=case]-> A). Never copy one scheme's shape into the other.
- relative clauses and other DEEP relations: in SUD they live in the deep slot, written -[1=mod, deep=relcl]-> (NEVER 2=relcl); in UD relcl is an ordinary subtype, -[1=acl, 2=relcl]->. Agents of passives: SUD deep=agent.
- when the description names a word class ("the noun", "its verb"), restrict that node: nouns usually mean [upos=NOUN|PROPN|PRON] as attachment targets, verbs [upos=VERB].

TRAPS
- Grew adds a virtual root node __0__ per sentence with an edge to the real root. A broad scope pattern { GOV -> DEP } must exclude it: add without { GOV [form="__0__"] }. For "share of all words" use pattern { X [upos=*] } (the root has no upos). A scope naming a specific relation needs no exclusion.
- The response may not introduce new nodes. To say "the object is a pronoun", the object node must be bound in the scope.
- "head-initial" means the governor precedes the dependent: with { GOV << DEP }.
- Conditioning belongs in the SCOPE: "among two-token subjects, how many are inverted" restricts the scope (subtree_size in the scope) and tests only the order in the response. A condition placed in the response changes the denominator and with it the meaning.

EXAMPLES (SUD)
"How often does the subject follow its verb?" ->
{"kind":"ratio","scope":"pattern { GOV -[1=subj]-> DEP }","response":"with { GOV << DEP }","expression":"","aggregation":"avg","label":"subj after governor","explanation":"Of all subject relations, the share where the subject follows its governor."}

"Average distance between a word and its governor, ignoring direction" ->
{"kind":"aggregate","scope":"pattern { GOV -> DEP }\\nwithout { GOV [form=\\"__0__\\"] }","response":"","expression":"abs(delta(GOV, DEP))","aggregation":"avg","label":"mean dependency length","explanation":"The average absolute distance in words between a dependent and its governor."}

"Share of clauses where the object is a pronoun" ->
{"kind":"ratio","scope":"pattern { V -[1=comp,2=obj]-> O }","response":"with { O [upos=PRON] }","expression":"","aggregation":"avg","label":"pronominal objects","explanation":"Of all direct objects, the share that are pronouns."}

"Of subjects spanning exactly two words, how many follow their verb?" ->
{"kind":"ratio","scope":"pattern { V -[1=subj]-> S }\\nwith { S.subtree_size = 2 }","response":"with { V << S }","expression":"","aggregation":"avg","label":"2-token subjects after verb","explanation":"Of subjects whose subtree spans exactly two tokens, the share following their governor."}

If the description is not a measure over dependencies, respond with {"error": "<one sentence why not>"}.
Answer in the same language the user wrote in (the explanation only; Grew syntax is Grew syntax)."""


def _chat(model: str, messages: list[dict]) -> str:
    response = httpx.post(
        f"{OPENAI_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _parse(raw: str) -> dict:
    data = json.loads(raw)
    if "error" in data:
        return data
    spec = MeasureSpec(
        scope=str(data.get("scope", "")),
        response=str(data.get("response", "") or ""),
        kind="aggregate" if data.get("kind") == "aggregate" else "ratio",
        expression=str(data.get("expression", "") or ""),
        aggregation=str(data.get("aggregation", "avg") or "avg"),
        label=str(data.get("label", "") or ""),
    )
    spec.validate()  # raises with a message the model can act on
    _check_features(spec)
    return {
        "kind": spec.kind,
        "scope": spec.scope,
        "response": spec.response,
        "expression": spec.expression,
        "aggregation": spec.aggregation,
        "label": spec.label,
        "explanation": str(data.get("explanation", "") or ""),
    }


# ------------------------------------------------------------------------- chat mode
#
# The side panel: a conversation that can end in a two-axis proposal. Same Grew
# knowledge, same validation discipline -- a proposal's axes go through validate() and
# an invalid one goes back to the model once. The model never runs anything: the
# proposal is rendered with its comment, and the human's approval presses Plot.

CHAT_SYSTEM = SYSTEM_PROMPT + """

CHAT MODE. You are the typometrics assistant inside a plotting tool. The user talks to
you about typological comparisons ("I'd like to compare X and Y", "how do Slavic
languages behave for Z"). Reply conversationally in the user's language, briefly.

Output STRICT JSON:
{"reply": "<your message: what the measures will show, caveats, what to look for>",
 "proposal": null | {
   "x": {axis object as above: kind/scope/response/expression/aggregation/label},
   "y": null | {axis object},
   "languages": null | ["Language_Name", ...],
   "comment": "<one or two sentences: what each axis measures and how to read the plot>"}}

- Propose ONE plot at a time. Two axes when the user compares two measures; y=null for a
  one-dimensional strip.
- "languages": only when the user restricts the comparison (a language, a family, a
  list); use English UD directory names with underscores (Old_French, Ancient_Greek).
  For "all languages", null.
- If the request is unclear, ask instead of proposing (proposal: null).
- The plot is always per-language across the corpus: a measure "for French" still runs
  everywhere unless languages restricts it — say so when relevant.
- After results exist the user may ask you to interpret them; you will receive a table.
  Comment distribution, clusters by family, outliers, implicational shapes (empty
  corners). Never invent numbers not in the table; mention that sampled values carry
  uncertainty."""


def _clean_axis(data: dict) -> dict:
    spec = MeasureSpec(
        scope=str(data.get("scope", "")),
        response=str(data.get("response", "") or ""),
        kind="aggregate" if data.get("kind") == "aggregate" else "ratio",
        expression=str(data.get("expression", "") or ""),
        aggregation=str(data.get("aggregation", "avg") or "avg"),
        label=str(data.get("label", "") or ""),
    )
    spec.validate()
    _check_features(spec)
    return {
        "kind": spec.kind, "scope": spec.scope, "response": spec.response,
        "expression": spec.expression, "aggregation": spec.aggregation, "label": spec.label,
    }


def _clean_proposal(proposal: dict) -> dict:
    """A chat or analysis proposal, axes validated — raises on anything unusable."""
    return {
        "x": _clean_axis(proposal.get("x") or {}),
        "y": _clean_axis(proposal["y"]) if proposal.get("y") else None,
        "languages": proposal.get("languages") or None,
        "comment": str(proposal.get("comment", "") or ""),
    }


def chat(messages: list[dict], scheme: str, model: str | None = None) -> dict:
    """One chat turn. A returned proposal is guaranteed to validate; the reply is not
    guaranteed to be wise, which is why the proposal is approved, never auto-run."""
    model = model or DEFAULT_MODEL
    history = [
        {"role": m["role"], "content": str(m["content"])[:4000]}
        for m in messages[-16:]
        if m.get("role") in ("user", "assistant")
    ]
    prompt = [{"role": "system", "content": CHAT_SYSTEM + f"\n\nScheme: {scheme.upper()}"}]
    prompt += history
    started = time.perf_counter()
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = _chat(model, prompt)
        try:
            data = json.loads(raw)
            reply = str(data.get("reply", "")).strip()
            proposal = data.get("proposal")
            if proposal:
                proposal = _clean_proposal(proposal)
            if not reply:
                raise ValueError("empty reply")
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            prompt.append({"role": "assistant", "content": raw})
            prompt.append(
                {"role": "user", "content": f"Invalid: {last_error}. Return corrected JSON."}
            )
            continue
        return {
            "ok": True, "reply": reply, "proposal": proposal, "model": model,
            "attempts": attempt, "seconds": round(time.perf_counter() - started, 2),
        }
    return {
        "ok": False, "error": last_error, "model": model, "attempts": MAX_ATTEMPTS,
        "seconds": round(time.perf_counter() - started, 2),
    }


def analyze(x_label: str, y_label: str, scheme: str, points: list[dict],
            model: str | None = None, x_query: str = "", y_query: str = "",
            history: list[dict] | None = None) -> dict:
    """Commentary over computed results, plus up to three follow-up proposals — the
    analysis ends in things to click, not just things to read. Proposals go through the
    same validation as chat; an invalid batch goes back to the model once, and after
    that the prose survives with the bad proposals dropped: the commentary is the
    primary value, a lost follow-up is not worth losing it.

    `history` and the axis queries are what keep the turn coherent: the button sends
    whatever plot is on screen, and a user who just asked about something else must be
    told the plot is not their question — not handed an answer that pretends it is."""
    model = model or DEFAULT_MODEL
    table = "\n".join(
        f"{p.get('language', '?')}\t{p.get('family', '?')}\t{p.get('x')}"
        + (f"\t{p.get('y')}" if y_label else "")
        for p in points[:250]
    )
    queries = ""
    if x_query.strip():
        queries = f"\nThe plotted X axis computes:\n{x_query.strip()}\n"
        if y_label and y_query.strip():
            queries += f"The plotted Y axis computes:\n{y_query.strip()}\n"
    content = (
        f"Scheme: {scheme}. X = {x_label}" + (f", Y = {y_label}" if y_label else "")
        + f".{queries}\nlanguage\tfamily\tx" + ("\ty" if y_label else "") + f"\n{table}\n\n"
        "Interpret this typologically for a linguist: overall distribution, family "
        "clusters, notable outliers (name them), implicational patterns if the shape "
        "suggests any. 150-250 words.\n"
        "This analyses THE PLOT CURRENTLY ON SCREEN. If the conversation above was "
        "heading somewhere else — the user asked about a different measure and never "
        "plotted it — open with one sentence saying so, analyse the plotted data "
        "anyway, and re-issue the fitting proposal for their actual question as a "
        "follow-up. If plot and conversation match, answer the user's question "
        "directly from the numbers.\n"
        "Then propose 1-3 FOLLOW-UP plots that would sharpen this analysis, each with a "
        "one-sentence comment saying what it would settle. Good follow-ups: the same "
        "measures zoomed into one interesting family ('languages' = its members, copied "
        "exactly from the table); a complementary measure that would explain an outlier "
        "or test the implicational reading; a finer measure restricted to one notable "
        "language. Do not re-propose the current plot unchanged.\n"
        'Output JSON {"reply": "...", "proposals": [{"x": …, "y": null | …, '
        '"languages": null | […], "comment": "…"}, …]} — axes exactly as in chat mode; '
        '"proposals": [] if nothing is worth a follow-up.'
    )
    turns = [
        {"role": m["role"], "content": str(m["content"])[:4000]}
        for m in (history or [])[-8:]
        if m.get("role") in ("user", "assistant")
    ]
    prompt = [
        {"role": "system", "content": CHAT_SYSTEM + f"\n\nScheme: {scheme.upper()}"},
        *turns,
        {"role": "user", "content": content},
    ]
    started = time.perf_counter()
    raw = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = _chat(model, prompt)
        try:
            data = json.loads(raw)
            reply = str(data.get("reply", "")).strip()
            proposals = [_clean_proposal(p) for p in (data.get("proposals") or [])[:3]]
            if not reply:
                raise ValueError("empty reply")
        except Exception as exc:  # noqa: BLE001 -- json or validation, both go back once
            prompt.append({"role": "assistant", "content": raw})
            prompt.append({
                "role": "user",
                "content": f"Invalid: {type(exc).__name__}: {exc}. Return corrected JSON.",
            })
            continue
        return {
            "ok": True, "reply": reply, "proposals": proposals, "model": model,
            "attempts": attempt, "seconds": round(time.perf_counter() - started, 2),
        }
    # Salvage the prose: keep the reply if the last raw parses at all (dropping any
    # still-invalid proposals), else treat the raw text as the reply.
    proposals = []
    try:
        data = json.loads(raw)
        reply = str(data.get("reply", "")).strip() or raw.strip()
        for entry in (data.get("proposals") or [])[:3]:
            try:
                proposals.append(_clean_proposal(entry))
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001 -- prose in, prose out
        reply = raw.strip()
    return {
        "ok": bool(reply), "reply": reply, "proposals": proposals, "model": model,
        "attempts": MAX_ATTEMPTS, "seconds": round(time.perf_counter() - started, 2),
    }


def translate(text: str, scheme: str, model: str | None = None) -> dict:
    """Description -> validated measure fields, or an honest failure.

    Never returns an unvalidated query: the second attempt gets the first attempt's
    output and the validator's error, and if that also fails, the caller gets the error,
    not the query.
    """
    model = model or DEFAULT_MODEL
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Scheme: {scheme.upper()}\n\n{text.strip()}"},
    ]
    started = time.perf_counter()
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = _chat(model, messages)
        try:
            result = _parse(raw)
        except Exception as exc:  # noqa: BLE001 -- json or validation, both go back once
            last_error = f"{type(exc).__name__}: {exc}"
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That query does not validate: {last_error}\n"
                        "Return corrected JSON in the same format."
                    ),
                }
            )
            continue
        if "error" in result:
            return {
                "ok": False, "refusal": result["error"], "model": model,
                "attempts": attempt, "seconds": round(time.perf_counter() - started, 2),
            }
        return {
            "ok": True, **result, "model": model, "attempts": attempt,
            "seconds": round(time.perf_counter() - started, 2),
        }
    return {
        "ok": False, "error": last_error, "model": model,
        "attempts": MAX_ATTEMPTS, "seconds": round(time.perf_counter() - started, 2),
    }
