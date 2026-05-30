#!/usr/bin/env python3
"""Run TaxBench-AU against an OpenAI-compatible endpoint or a CLI agent.

Outputs a CSV with columns: id, answer, raw_response.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib import request, error


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = ROOT / "data" / "question.csv"
DEFAULT_KEY = ROOT / "data" / "exam.csv"
DEFAULT_OUT = ROOT / "runs" / "answers.csv"


def build_prompt(row: dict[str, str], template: str | None = None) -> str:
    if template:
        return template.format(
            id=row.get("id", ""),
            topic=row.get("topic", ""),
            year_of_income=row.get("year_of_income", ""),
            question=row["question"],
        )
    return (
        "Answer this Australian tax question.\n"
        "Return only A, B, C, or D.\n\n"
        f"{row['question']}\n"
    )


def parse_answer(text: str) -> str:
    raw = (text or "").strip()
    patterns = [
        r"^\s*([ABCD])\s*[\).]?\s*$",
        r"(?:answer|option|choice|final)\s*(?:is|:|-)?\s*\(?([ABCD])\)?\b",
        r"\b([ABCD])\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, raw, flags=re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return ""


def call_openai_compatible(prompt: str, args: argparse.Namespace) -> str:
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "")
    base_url = (args.base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = args.model or os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL") or "gpt-4o-mini"
    url = f"{base_url}/chat/completions"
    body = {
        "model": model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=args.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    return data["choices"][0]["message"]["content"]


def call_command(prompt: str, row: dict[str, str], args: argparse.Namespace) -> str:
    env = os.environ.copy()
    env.update(
        {
            "TAXBENCH_PROMPT": prompt,
            "TAXBENCH_ID": row.get("id", ""),
            "TAXBENCH_TOPIC": row.get("topic", ""),
            "TAXBENCH_YEAR": row.get("year_of_income", ""),
            "TAXBENCH_AGENT_CWD": str(args.agent_cwd or ""),
        }
    )
    proc = subprocess.run(
        args.command,
        shell=True,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=args.timeout,
        env=env,
        cwd=args.agent_cwd,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"command exited {proc.returncode}")
    return proc.stdout.strip()


def load_questions(path: Path, limit: int | None, ids: set[str] | None) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if ids:
        rows = [r for r in rows if r["id"] in ids]
    if limit is not None:
        rows = rows[:limit]
    return rows


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "answer", "raw_response"])
        w.writeheader()
        w.writerows(rows)


def grade(out_path: Path, key_path: Path) -> None:
    sys.path.insert(0, str(ROOT))
    from verifier import grade as grade_submission  # type: ignore

    grade_submission(str(out_path), str(key_path))


def prepare_agent_workspace(path: Path, expose_calculator: bool) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.txt").write_text(
        "TaxBench-AU isolated agent workspace.\n"
        "The benchmark answer key is not present here.\n"
        "Answer from the prompt. Return only A, B, C, or D.\n",
        encoding="utf-8",
    )
    if expose_calculator:
        shutil.copy2(ROOT / "verifier.py", path / "verifier.py")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run TaxBench-AU against a model or CLI agent.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--openai", action="store_true", help="Use an OpenAI-compatible /chat/completions endpoint.")
    mode.add_argument("--command", help="Shell command for a CLI agent. Prompt is sent on stdin and TAXBENCH_PROMPT.")
    p.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    p.add_argument("--key", type=Path, default=DEFAULT_KEY)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--limit", type=int, help="Run only the first N questions.")
    p.add_argument("--ids", help="Comma-separated question ids, e.g. Q001,Q002.")
    p.add_argument("--model", help="Model name for OpenAI-compatible mode. Defaults to OPENAI_MODEL, MODEL, or gpt-4o-mini.")
    p.add_argument("--base-url", help="Base URL for OpenAI-compatible mode. Defaults to OPENAI_BASE_URL or https://api.openai.com/v1.")
    p.add_argument("--api-key", help="API key. Defaults to OPENAI_API_KEY.")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=8)
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between questions.")
    p.add_argument("--no-grade", action="store_true", help="Write answers without running verifier.py grade.")
    p.add_argument(
        "--prompt-template",
        type=Path,
        help="Optional custom prompt template file. It may contain {question}, {id}, {topic}, and {year_of_income}.",
    )
    p.add_argument(
        "--agent-cwd",
        type=Path,
        help="Working directory for a CLI agent. Defaults to a temporary directory with no answer key.",
    )
    p.add_argument(
        "--expose-calculator",
        action="store_true",
        help="Copy verifier.py into the isolated CLI workspace so agents can use `python3 verifier.py calc`.",
    )
    args = p.parse_args(argv)

    ids = {x.strip() for x in args.ids.split(",")} if args.ids else None
    questions = load_questions(args.questions, args.limit, ids)
    if not questions:
        raise SystemExit("No questions selected.")
    prompt_template = args.prompt_template.read_text(encoding="utf-8") if args.prompt_template else None

    temp_agent_dir = None
    if args.command:
        if args.agent_cwd:
            args.agent_cwd = args.agent_cwd.resolve()
        else:
            temp_agent_dir = tempfile.TemporaryDirectory(prefix="taxbench-agent-")
            args.agent_cwd = Path(temp_agent_dir.name)
        prepare_agent_workspace(args.agent_cwd, args.expose_calculator)
        print(f"Agent cwd: {args.agent_cwd}", file=sys.stderr)

    try:
        results: list[dict[str, str]] = []
        for i, row in enumerate(questions, 1):
            prompt = build_prompt(row, prompt_template)
            print(f"[{i}/{len(questions)}] {row['id']} {row.get('topic', '')}", file=sys.stderr)
            try:
                raw = call_openai_compatible(prompt, args) if args.openai else call_command(prompt, row, args)
                answer = parse_answer(raw)
            except Exception as exc:  # noqa: BLE001
                raw = f"ERROR: {exc}"
                answer = ""
            results.append({"id": row["id"], "answer": answer, "raw_response": raw})
            if args.sleep:
                time.sleep(args.sleep)

        write_rows(args.out, results)
        print(f"Wrote {args.out}", file=sys.stderr)
        if not args.no_grade:
            grade(args.out, args.key)
    finally:
        if temp_agent_dir:
            temp_agent_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
