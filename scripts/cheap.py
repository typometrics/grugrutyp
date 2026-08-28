#!/usr/bin/env python3
"""Send a task to a cheaper model over its OpenAI-compatible API.

The orchestrator (Opus 5) calls this via Bash, reads the draft, and decides what to keep.
That division is the point: the cheap model does bulk generation, the orchestrator keeps
context and judgement. See setup.md section 4.

    ./scripts/cheap.py --model deepseek-chat \\
        --system "$(cat docs/grew-to-cypher.md)" \\
        --file backend/grugrutyp/translate/ast.py \\
        --task "write the Cypher emitter for edge clauses per section 2"

Keys come from ~/.config/grugrutyp/models.env -- never from the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "models.yaml"
ENV_FILE = Path.home() / ".config" / "grugrutyp" / "models.env"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def load_registry() -> dict:
    """Minimal YAML reader for the flat two-level models.yaml -- avoids a PyYAML dep."""
    models: dict[str, dict] = {}
    current: str | None = None
    for raw in REGISTRY.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            current = raw.rstrip(":").strip()
            models[current] = {}
        elif current:
            key, _, value = raw.strip().partition(":")
            models[current][key.strip()] = value.strip().strip('"').strip("[]").strip()
    return models


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--task", help="what to produce")
    parser.add_argument("--system", default="", help="spec / context text")
    parser.add_argument("--file", action="append", default=[], help="files to include")
    parser.add_argument("--max-tokens", type=int, default=8000)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--list", action="store_true", help="show the registry and exit")
    args = parser.parse_args()

    load_env(ENV_FILE)
    registry = load_registry()

    if args.list:
        for name, spec in registry.items():
            print(f"{name:<22} {spec.get('use_for', '')}")
        return 0

    if not args.model or not args.task:
        parser.error("--model and --task are required (use --list to see the registry)")

    if args.model not in registry:
        print(
            f"unknown model '{args.model}'. Known: {', '.join(registry)}",
            file=sys.stderr,
        )
        return 2

    spec = registry[args.model]
    api_key = os.environ.get(spec.get("api_key_env", ""))
    base_url = os.environ.get(spec.get("base_url_env", ""))
    if not api_key or not base_url:
        print(
            f"missing {spec.get('api_key_env')} / {spec.get('base_url_env')}.\n"
            f"Put them in {ENV_FILE} (chmod 600) -- see setup.md section 3.",
            file=sys.stderr,
        )
        return 3

    context = []
    for path in args.file:
        text = Path(path).read_text(encoding="utf-8")
        context.append(f"--- {path} ---\n{text}")

    user_content = args.task
    if context:
        user_content = "\n\n".join(context) + "\n\n--- task ---\n" + args.task

    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": user_content})

    payload = json.dumps(
        {
            "model": args.model,
            "messages": messages,
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
        }
    ).encode()

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        print(f"{exc.code} {exc.reason}: {exc.read().decode()[:500]}", file=sys.stderr)
        return 4

    print(body["choices"][0]["message"]["content"])
    usage = body.get("usage", {})
    if usage:
        print(
            f"\n[{args.model}: {usage.get('prompt_tokens')} in, "
            f"{usage.get('completion_tokens')} out]",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
