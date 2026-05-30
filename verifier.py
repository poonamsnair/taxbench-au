#!/usr/bin/env python3
"""Australian Tax MCQ — verifier & calculator tool.

Three uses:

  1) Grade your agent's answers against the key:
       python verifier.py grade my_answers.csv
     where my_answers.csv has columns:  id,answer   (answer = A/B/C/D or a number)

  2) Recompute a single case's answer from its stored Python verifier:
       python verifier.py verify --id Q001

  3) Use the safe calculator as a TOOL for your agent while it solves a question:
       python verifier.py calc "(880000 - 615000) * 0.5"     ->  132500.0

It reads data/exam.csv (the answer key) by default.
"""
import argparse
import ast
import csv
import json
import operator
import os
import re

# ---- safe arithmetic evaluator: numbers, + - * / // % **, min/max/round/abs ----
_B = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
      ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
      ast.Mod: operator.mod, ast.Pow: operator.pow}
_U = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_F = {"min": min, "max": max, "round": round, "abs": abs}


def calc(expr, params=None):
    """Evaluate an arithmetic expression safely. `params` binds variable names."""
    params = params or {}

    def ev(n):
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            return params[n.id]
        if isinstance(n, ast.BinOp):
            return _B[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp):
            return _U[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _F:
            return _F[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"disallowed expression: {ast.dump(n)}")

    return ev(ast.parse(expr, mode="eval").body)


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KEY = os.path.join(HERE, "data", "exam.csv")


def load_key(path=None):
    with open(path or DEFAULT_KEY) as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def _num(s):
    return float(re.sub(r"[^0-9.\-]", "", str(s)))


def is_right(answer, key_row, tol=1.0):
    a = str(answer).strip().upper()
    if not a:
        return False
    if a in ("A", "B", "C", "D"):
        return a == key_row["answer_label"]
    try:
        return abs(_num(answer) - _num(key_row["numeric_answer"])) <= tol
    except ValueError:
        return False


def grade(submission, key_path=None):
    key = load_key(key_path)
    with open(submission) as f:
        subs = list(csv.DictReader(f))
    n = correct = 0
    by = {}
    for s in subs:
        cid = s.get("id")
        if cid not in key:
            continue
        k = key[cid]
        n += 1
        ok = is_right(s.get("answer", ""), k)
        t = k["topic"]
        by.setdefault(t, [0, 0])
        by[t][1] += 1
        if ok:
            correct += 1
            by[t][0] += 1
    print(f"score: {correct}/{n} = {correct/n:.1%}" if n else "no matching ids found")
    for t, (c, tot) in sorted(by.items()):
        print(f"  {t:26s} {c}/{tot} = {c/tot:.1%}")
    return correct, n


def verify(cid, key_path=None):
    k = load_key(key_path)[cid]
    comp = json.loads(k["python_verifier"])
    got = calc(comp["formula"], comp["params"])
    match = abs(got - _num(k["numeric_answer"])) <= 1.0
    print(f"{cid}: {comp['formula']}")
    print(f"   params={comp['params']}")
    print(f"   verifier -> {got}   stated answer -> {k['numeric_answer']} ({k['answer_label']})   match={match}")
    return match


def check(cid, answer, key_path=None):
    k = load_key(key_path)[cid]
    ok = is_right(answer, k)
    print(f"{cid}: {'CORRECT' if ok else 'INCORRECT'}  "
          f"(key: {k['answer_label']} = {k['correct_answer']})")
    return ok


def main():
    ap = argparse.ArgumentParser(description="ATO Tax MCQ verifier & calculator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade", help="grade a submission CSV (columns id,answer)")
    g.add_argument("submission")
    g.add_argument("--key", help="path to exam.csv (default: data/exam.csv)")
    v = sub.add_parser("verify", help="recompute a case's answer from its stored formula")
    v.add_argument("--id", required=True)
    v.add_argument("--key", help="path to exam.csv (default: data/exam.csv)")
    c = sub.add_parser("check", help="check one answer")
    c.add_argument("--id", required=True)
    c.add_argument("--answer", required=True)
    c.add_argument("--key", help="path to exam.csv (default: data/exam.csv)")
    cc = sub.add_parser("calc", help="safe calculator tool for your agent")
    cc.add_argument("expr")
    a = ap.parse_args()
    if a.cmd == "grade":
        grade(a.submission, a.key)
    elif a.cmd == "verify":
        verify(a.id, a.key)
    elif a.cmd == "check":
        check(a.id, a.answer, a.key)
    elif a.cmd == "calc":
        print(calc(a.expr))


if __name__ == "__main__":
    main()
