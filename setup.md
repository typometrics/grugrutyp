# setup.md — how to run this build process

Answers the four questions in `ideas.md`:

> * long time running on this machine, how to connect and get this running?
> * orchestrated by opus 5, but using cheaper models for coding.
> * should i put the api access codes such as for deepseek into an .env file? where?
> * do the other models need description to help opus decide which model to use for what?

---

## 1. The machine

Everything runs on the box that already serves typometrics.elizia.net.

| | |
|---|---|
| CPU / RAM / disk | 8 cores, 31 GB RAM, 1.1 TB free on `/home` |
| OS | Ubuntu, Linux 7.0.0-29 |
| Python | 3.14.4 system; grugrutyp uses its **own venv** — do not touch the system one |
| Node | v22.22.1, npm 9.2.0 |
| Docker | 29.1.3 — Neo4j runs here |
| Already running | nginx, mysql, ~10 systemd app services, pm2. **Be a good neighbour: cap Neo4j's heap.** |

### Already installed for this project (2026-08-28)

```
/opt/opam/grew/bin/grew              1.21.0     ← Grew CLI
/opt/opam/grew/bin/grewpy_backend    0.6.2      ← backend for the grewpy Python lib
```

opam root is `/opt/opam`, switch `grew`. To use them:

```bash
export OPAMROOT=/opt/opam
eval "$(opam env --switch=grew)"     # puts grew + grewpy_backend on PATH
```

These are the **test oracle**, not the production engine (`docs/grew-to-cypher.md` §9).

---

## 2. Connecting, and surviving a long-running build

`ssh` sessions die; the build does not have to.

### Persistent session

```bash
ssh <this-box>
tmux new -s grugrutyp          # or: tmux attach -t grugrutyp
cd /home/typometrics/grugrutyp
claude
```

Detach with `Ctrl-b d`. The session, and anything running in it, survives disconnection.
**Always start Claude Code inside tmux for this project** — a Phase 1 translator session
runs for hours.

### Resuming a conversation

```bash
claude --continue          # resume the most recent conversation in this directory
claude --resume            # pick from a list
```

Conversation state is per working directory, so always start from
`/home/typometrics/grugrutyp`.

### Long jobs belong to the system, not to the session

Imports, downloads and full-corpus benchmarks must not depend on a terminal:

```bash
setsid nohup ./scripts/import_neo4j.py --all > logs/import.log 2>&1 < /dev/null &
```

or, for anything that should come back after a reboot, a systemd unit (§6).

### CLAUDE.md

Put project conventions in `/home/typometrics/grugrutyp/CLAUDE.md` — it is loaded into
every session automatically. Keep it short: venv path, how to run tests, the "never touch
`djangotypometrics/` or `quasartypometrics/`" rule, and the model-routing table from §4.

---

## 3. Secrets: where the API keys go

**Short answer: yes, an `.env` file — but not one, three, and none of them in git.**

| what | where | mode | who reads it |
|---|---|---|---|
| model API keys (DeepSeek, Qwen) | `~/.config/grugrutyp/models.env` | `600` | your shell / the cheap-model wrapper |
| app runtime secrets (Neo4j password) | `/home/typometrics/grugrutyp/.env` | `600`, gitignored | FastAPI, `import_neo4j.py` |
| service secrets | `/etc/grugrutyp/env` | `600 root:root` | systemd `EnvironmentFile=` |

```bash
mkdir -p ~/.config/grugrutyp
cat > ~/.config/grugrutyp/models.env <<'EOF'
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
QWEN_API_KEY=sk-...
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
EOF
chmod 600 ~/.config/grugrutyp/models.env
```

Load it in your shell (`~/.bashrc`): `set -a; . ~/.config/grugrutyp/models.env; set +a`

Rules:

1. `.gitignore` must contain `.env`, `*.env`, `data/`, `logs/` **before the first commit**.
   A key that reaches a git history is a rotated key.
2. Never put keys in `.claude/settings.json` — that file is meant to be shared/committed.
   `.claude/settings.local.json` is gitignored and is the right place for *machine-local
   non-secret* settings; keys still belong in the env files above.
3. Never put keys in a systemd unit file (world-readable); use `EnvironmentFile=`.
4. The Neo4j password is generated once, stored in `/home/typometrics/grugrutyp/.env`,
   and Neo4j is bound to `127.0.0.1` only.

---

## 4. Orchestration: Opus 5 driving, cheaper models coding

### The honest constraint

Claude Code's own model selector understands Anthropic models. Its subagents
(`.claude/agents/*.md`) take a `model:` field, but that field selects among **Anthropic**
models — you cannot write `model: deepseek-chat` there and have it work.

So there are two real routes to "cheap models do the coding":

| route | how | verdict |
|---|---|---|
| **A. Cheap models as a tool** | a small CLI, `scripts/cheap.py`, that talks to DeepSeek/Qwen over their OpenAI-compatible APIs. Opus calls it via Bash, reviews the output, and applies it. | **Recommended.** Opus keeps full context and judgement; the cheap model does bulk generation. Nothing about the Claude Code session degrades. |
| **B. Gateway swap** | run a LiteLLM proxy, point `ANTHROPIC_BASE_URL` at it, and map the model slots (`ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`) onto DeepSeek/Qwen. | Works, but the mapping is global to the session and tool-calling fidelity through a translation proxy is not guaranteed. Reach for it only if A proves too slow. |

### Route A in practice

`scripts/cheap.py` — one file, no dependencies beyond `openai`:

```bash
# generate a first draft of a mechanical module
./scripts/cheap.py --model deepseek-chat \
    --system "$(cat prompts/translator_emitter.md)" \
    --file backend/grugrutyp/translate/ast.py \
    --task "write the Cypher emitter for edge clauses per docs/grew-to-cypher.md §2" \
  > /tmp/draft.py
```

Opus then reads `/tmp/draft.py`, fixes it, and writes the real file. The division of
labour that actually pays:

| give to a cheap model | keep with Opus 5 |
|---|---|
| boilerplate: pydantic models, CRUD endpoints, Quasar component scaffolds | the Grew→Cypher semantics — a subtle bug here is invisible and poisons every result |
| mechanical translation: one more construct following an existing pattern | anything touching `docs/grew-to-cypher.md` §7 (the divergence table) |
| test *fixtures* and parametrised cases from a spec | deciding **what** to test, and reading failures |
| docstrings, type annotations, refactors with a green test suite | the phase gates in `plan.md` |

The rule: **a cheap model may write code that a test proves correct; it may not decide
what correct means.** Phase 1 has a differential oracle, so cheap models are safe there
*behind the test*. Phase 3's statistics have no oracle — keep them with Opus.

### Model registry

`models.yaml` in the repo root, read by `scripts/cheap.py`, and summarised in `CLAUDE.md`
so the orchestrator can pick without re-reading it:

```yaml
deepseek-chat:
  provider: deepseek
  strengths: [python, refactoring, boilerplate, long-context-editing]
  weaknesses: [novel algorithm design, subtle semantics]
  context: 128k
  use_for: "bulk Python: FastAPI endpoints, importer plumbing, pydantic schemas, test fixtures"

deepseek-reasoner:
  provider: deepseek
  strengths: [step-by-step reasoning, tricky logic, debugging]
  weaknesses: [slow, expensive relative to deepseek-chat]
  use_for: "a translator rule that resists the obvious encoding; a failing differential test nobody understands"

qwen3-coder-plus:
  provider: qwen
  strengths: [code generation, multilingual, javascript/vue]
  weaknesses: [less reliable on long English specs]
  use_for: "Quasar 2 / Vue 3 components, the reactive-dep-tree integration, CSS"
```

### Answering the fourth question directly

> *do the other models need description to help opus decide which model to use for what?
> how to do that?*

**Yes, and the description is what makes the routing work at all** — without it the
orchestrator has no basis for choosing and will just use whichever it saw last. Two places,
both needed:

1. **`models.yaml`** (above) — the machine-readable registry the wrapper validates against.
2. **A short table in `CLAUDE.md`** — because that file is in context for every turn,
   whereas `models.yaml` is only in context if something reads it. Keep it to five lines:

   ```markdown
   ## Model routing
   Bulk Python / boilerplate → ./scripts/cheap.py --model deepseek-chat
   Vue / Quasar components   → ./scripts/cheap.py --model qwen3-coder-plus
   Hard debugging            → ./scripts/cheap.py --model deepseek-reasoner
   Grew→Cypher semantics, statistics, phase gates → do it yourself, do not delegate
   ```

Write the *use_for* lines as decision rules ("use for X when Y"), not as marketing
adjectives. "Good at code" routes nothing; "bulk Python where a test already exists"
routes correctly.

### Subagents (Anthropic models) are still worth defining

For work that stays inside Claude Code, `.claude/agents/*.md`:

```markdown
---
name: translator-tester
description: Runs the Grew→Cypher differential suite and reports mismatches. Use after any change under backend/grugrutyp/translate/.
tools: Bash, Read, Grep
model: sonnet
---
Run `pytest tests/test_differential.py -x -q`. For each failure report the Grew request,
the emitted Cypher, both counts, and your hypothesis. Do not edit files.
```

Cheap in tokens, and it keeps the long-running orchestrator's context clean.

---

## 5. Development environment

```bash
cd /home/typometrics/grugrutyp
python3 -m venv .venv && . .venv/bin/activate
pip install fastapi uvicorn neo4j lark pydantic pytest httpx conllu
pip install grewpy                      # oracle only; needs the opam env from §1
```

Neo4j:

```bash
docker run -d --name grugrutyp-neo4j --restart unless-stopped \
  -p 127.0.0.1:7474:7474 -p 127.0.0.1:7687:7687 \
  -v /home/typometrics/grugrutyp/data/neo4j/data:/data \
  -e NEO4J_AUTH=neo4j/"$NEO4J_PASSWORD" \
  -e NEO4J_server_memory_heap_max__size=8G \
  -e NEO4J_server_memory_pagecache_size=4G \
  -e NEO4J_db_transaction_timeout=60s \
  neo4j:5.26-community
```

The heap/pagecache caps and the transaction timeout are not optional — this box runs ten
other services, and a user query must not be able to wedge it.

Frontend:

```bash
cd frontend && npm install && npx quasar dev      # dev server, proxy /api to :8020
npx quasar build                                  # → dist/spa, served by nginx
```

---

## 6. Deploying alongside the live site

`ideas.md`: *"for the moment don't erase the config of the current typometrics, but build
this in a subfolder."*

nginx, added to `/etc/nginx/sites-available/typometrics` — **added, not replacing**:

```nginx
location /grugrutyp/api/ {
    proxy_pass http://127.0.0.1:8020/;
    proxy_set_header Host $host;
    proxy_read_timeout 300s;          # SSE: measure streams run long
    proxy_buffering off;              # SSE: must not buffer
}
location /grugrutyp/ {
    alias /home/typometrics/grugrutyp/frontend/dist/spa/;
    try_files $uri $uri/ /grugrutyp/index.html;
}
```

systemd `/etc/systemd/system/grugrutyp-api.service`:

```ini
[Unit]
Description=grugrutyp FastAPI backend
After=network.target docker.service

[Service]
User=typometrics
WorkingDirectory=/home/typometrics/grugrutyp
EnvironmentFile=/etc/grugrutyp/env
ExecStart=/home/typometrics/grugrutyp/.venv/bin/uvicorn grugrutyp.main:app --host 127.0.0.1 --port 8020
Restart=always

[Install]
WantedBy=multi-user.target
```

Port 8020 is free (7001 = the Django app; other services use 8000-8019).

The existing site keeps working throughout. Nothing under `djangotypometrics/` or
`quasartypometrics/` is edited, at all, until Phase 4 says otherwise.
