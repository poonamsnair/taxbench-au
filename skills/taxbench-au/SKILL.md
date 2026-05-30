---
name: taxbench-au
description: Run, grade, smoke test, or report the TaxBench-AU Australian tax MCQ benchmark against Codex, Claude Code, another CLI agent, or an OpenAI-compatible model endpoint.
metadata:
  short-description: Run TaxBench-AU evals
---

# TaxBench-AU

Run the repo's benchmark harness. Do not create a new eval runner.

## Quick start

```bash
python3 verifier.py verify --id Q001
python3 -m py_compile verifier.py scripts/run_eval.py
```

Expected `Q001`: `C`, `$1,180`, `match=True`.

```text
Answer this Australian tax question.
Return only A, B, C, or D.

{question}
```

Use this prompt for comparable scores. If using `--prompt-template`, report the run as custom-prompt.

## Run

```bash
export OPENAI_API_KEY=...
export OPENAI_MODEL=...
python3 scripts/run_eval.py --openai --limit 3 --out runs/openai_smoke.csv

python3 scripts/run_eval.py \
  --command 'your-agent-command-that-prints-one-letter' \
  --limit 3 \
  --out runs/agent_smoke.csv

python3 scripts/run_eval.py \
  --command 'codex --ask-for-approval never exec --skip-git-repo-check --color never --ephemeral --sandbox read-only -C "$PWD" -' \
  --limit 3 \
  --out runs/codex_smoke.csv
```

Remove `--limit 3` for the full 156-question eval.

## Options

| Option | Use |
| --- | --- |
| `--prompt-template <file>` | Custom prompt. Report as custom-prompt. |
| `--expose-calculator` | Copy `verifier.py` into the agent workspace for `python3 verifier.py calc`. |
| `--agent-cwd <dir>` | Override agent workspace. Do not use repo root for serious runs. |
| `--no-grade` | Save answers without grading. |
| `--ids Q001,Q002` | Run selected questions only. |

## Guardrails

- CLI agents run in a temporary workspace by default.
- Do not let the answering agent read `data/answer.csv` or `data/exam.csv`.
- Report tool access: web, retrieval, tax DB, calculator.
- Say "closed-book" only when web/retrieval/tax DB tools were disabled.

## Grade

```bash
python3 verifier.py grade runs/my_answers.csv
```

Input CSV needs `id,answer`.

## Report

Report: command, model/agent, prompt mode, tool mode, answer-key isolation, attempted questions, score, output CSV.
