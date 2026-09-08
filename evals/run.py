"""Score the model-facing reads against the golden set.

    python -m evals.run            # all cases
    python -m evals.run --no-llm   # resolver only, no model calls

Three things are scored, each against the answer a person wrote into
evals/golden_set.jsonl:

- intent: the same prompt and schema intake_triage uses (classify_intent)
- invoice: the resolver, sender company plus quoted number or amount
- rate: the same prompt and schema extract_claim uses, only for cases
  whose expected intent is discount_request

Every run writes evals/results/<timestamp>.json with per-case outcomes so
a prompt change can be compared to the run before it. This is the
evaluation half of the feedback rail in the PRD: change a prompt, run
this, read the failures, then decide.
"""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.resolver import resolve_invoice

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden_set.jsonl"
RESULTS = HERE / "results"


def load_cases() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(use_llm: bool) -> dict:
    if use_llm:
        from src.orchestration.nodes import classify_intent, extract_claim_rate
    cases = load_cases()
    rows, confusion = [], Counter()
    for case in cases:
        text = f"{case['subject']}\n{case['body']}"
        hit = resolve_invoice(case["sender"], text)
        got_invoice = hit[1] if hit else None
        row = {"id": case["id"], "invoice_ok": got_invoice == case["invoice"], "got_invoice": got_invoice,
               "want_invoice": case["invoice"], "note": case.get("note")}
        if use_llm:
            intent, _ = classify_intent(case["body"])
            row.update({"intent_ok": intent == case["intent"], "got_intent": intent, "want_intent": case["intent"]})
            confusion[(case["intent"], intent)] += 1
            if case["intent"] == "discount_request":
                rate, _ = extract_claim_rate(case["body"])
                want = case["rate"]
                ok = (rate is None and want is None) or (rate is not None and want is not None and abs(rate - want) < 1e-4)
                row.update({"rate_ok": ok, "got_rate": rate, "want_rate": want})
        rows.append(row)

    def score(key):
        scored = [r for r in rows if key in r]
        return (sum(r[key] for r in scored), len(scored))

    summary = {"cases": len(rows), "invoice": score("invoice_ok")}
    if use_llm:
        summary["intent"] = score("intent_ok")
        summary["rate"] = score("rate_ok")
        per_intent = defaultdict(lambda: [0, 0])
        for r in rows:
            per_intent[r["want_intent"]][1] += 1
            per_intent[r["want_intent"]][0] += int(r["intent_ok"])
        summary["intent_by_class"] = {k: tuple(v) for k, v in per_intent.items()}
        summary["confusions"] = {f"{w} -> {g}": n for (w, g), n in confusion.items() if w != g}
    return {"summary": summary, "rows": rows, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()
    report = run(use_llm=not args.no_llm)
    s = report["summary"]

    def pct(pair):
        return f"{pair[0]}/{pair[1]} ({100 * pair[0] / pair[1]:.0f}%)" if pair[1] else "n/a"

    print(f"cases: {s['cases']}")
    print(f"resolver: {pct(s['invoice'])}")
    if "intent" in s:
        print(f"intent:   {pct(s['intent'])}  by class: " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in s["intent_by_class"].items()))
        print(f"rate:     {pct(s['rate'])}")
        if s["confusions"]:
            print("confusions: " + ", ".join(f"{k} x{v}" for k, v in s["confusions"].items()))
    failures = [r for r in report["rows"] if not all(r.get(k, True) for k in ("intent_ok", "invoice_ok", "rate_ok"))]
    for r in failures:
        parts = []
        if not r.get("intent_ok", True):
            parts.append(f"intent {r['got_intent']} (want {r['want_intent']})")
        if not r["invoice_ok"]:
            parts.append(f"invoice {r['got_invoice']} (want {r['want_invoice']})")
        if not r.get("rate_ok", True):
            parts.append(f"rate {r['got_rate']} (want {r['want_rate']})")
        print(f"  FAIL {r['id']}: " + "; ".join(parts) + (f"  [{r['note']}]" if r.get("note") else ""))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{report['ran_at'].replace(':', '-')}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"written {out.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
