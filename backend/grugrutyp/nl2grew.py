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

import httpx

from .engine.neo4j_engine import load_env
from .measure import MeasureSpec

load_env()

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

SCHEME DIFFERENCES THAT CHANGE MEANING
- subject: SUD -[1=subj]->, UD -[1=nsubj]->. direct object: SUD -[1=comp,2=obj]->, UD -[1=obj]->. adjectival modifier: SUD -[1=mod]-> with DEP [upos=ADJ], UD -[1=amod]->.
- ALWAYS write the relation in feature form (-[1=nsubj]->, -[1=case]->) in BOTH schemes: the 1= form subsumes subtypes (nsubj:pass, nsubj:outer, aux:caus…), which is almost always what a typological measure means. A plain -[nsubj]-> matches only the exact label — use it only when the user explicitly excludes subtypes.
- adpositions: SUD makes the adposition the governor of the noun (A -> N with A [upos=ADP]); UD makes it a case dependent (N -[1=case]-> A). Never copy one scheme's shape into the other.
- when the description names a word class ("the noun", "its verb"), restrict that node: nouns usually mean [upos=NOUN|PROPN|PRON] as attachment targets, verbs [upos=VERB].

TRAPS
- Grew adds a virtual root node __0__ per sentence with an edge to the real root. A broad scope pattern { GOV -> DEP } must exclude it: add without { GOV [form="__0__"] }. For "share of all words" use pattern { X [upos=*] } (the root has no upos). A scope naming a specific relation needs no exclusion.
- The response may not introduce new nodes. To say "the object is a pronoun", the object node must be bound in the scope.
- "head-initial" means the governor precedes the dependent: with { GOV << DEP }.

EXAMPLES (SUD)
"How often does the subject follow its verb?" ->
{"kind":"ratio","scope":"pattern { GOV -[1=subj]-> DEP }","response":"with { GOV << DEP }","expression":"","aggregation":"avg","label":"subj after governor","explanation":"Of all subject relations, the share where the subject follows its governor."}

"Average distance between a word and its governor, ignoring direction" ->
{"kind":"aggregate","scope":"pattern { GOV -> DEP }\\nwithout { GOV [form=\\"__0__\\"] }","response":"","expression":"abs(delta(GOV, DEP))","aggregation":"avg","label":"mean dependency length","explanation":"The average absolute distance in words between a dependent and its governor."}

"Share of clauses where the object is a pronoun" ->
{"kind":"ratio","scope":"pattern { V -[1=comp,2=obj]-> O }","response":"with { O [upos=PRON] }","expression":"","aggregation":"avg","label":"pronominal objects","explanation":"Of all direct objects, the share that are pronouns."}

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
    return {
        "kind": spec.kind,
        "scope": spec.scope,
        "response": spec.response,
        "expression": spec.expression,
        "aggregation": spec.aggregation,
        "label": spec.label,
        "explanation": str(data.get("explanation", "") or ""),
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
