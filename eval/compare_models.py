"""Compara endpoints FM en el mismo harness (eval/cases.jsonl) y escribe eval/models.md con la tabla.

    python eval/compare_models.py                       # Understand: llama-3.1-8b vs gpt-oss-20b vs llama-3.3-70b vs gpt-oss-120b
    python eval/compare_models.py --limit 30 --small databricks-gpt-oss-20b databricks-meta-llama-3-1-8b-instruct
    python eval/compare_models.py --main databricks-meta-llama-3-3-70b-instruct databricks-gpt-oss-120b   # it. 4, Verify/Respond

Criterio (ADR-02, pedido en PR it.3): se elige con el número — paired_accuracy, luego fp_action_rate, luego latencia p95 y costo/turno.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.run_eval import run  # noqa: E402

DEFAULT_SMALL = ["databricks-meta-llama-3-1-8b-instruct", "databricks-gpt-oss-20b", "databricks-meta-llama-3-3-70b-instruct", "databricks-gpt-oss-120b"]
COLS = ["act_accuracy", "abstain_accuracy", "paired_accuracy", "fp_action_rate", "ur", "ivr", "exact_match"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int); ap.add_argument("--cases")
    ap.add_argument("--small", nargs="*", help="endpoints a comparar en Understand"); ap.add_argument("--main", nargs="*", help="endpoints a comparar en Verify/Respond (it. 4)")
    ap.add_argument("--pause", type=float, default=1.0, help="segundos entre casos (cuota FM APIs)")
    a = ap.parse_args()
    role = "main" if a.main else "small"
    names = a.main or a.small or DEFAULT_SMALL
    rows = []
    for n in names:
        t0 = time.time()
        try:
            rep = run(a.limit, Path(a.cases) if a.cases else None, pause_s=a.pause, **{role: n})
            m = rep["all"]
            rows.append({"endpoint": n, **{c: m[c] for c in COLS}, "p50_ms": rep["latency_ms"]["p50"], "p95_ms": rep["latency_ms"]["p95"],
                         "usd_turn": rep["cost_usd_per_turn"], "groundedness": rep["groundedness"], "n": m["n"], "fallas": len(rep["failures"]), "wall_s": round(time.time() - t0), "r429": rep["runtime"]["retries_429"]})
            (ROOT / "eval" / "results").mkdir(parents=True, exist_ok=True)
            (ROOT / "eval" / "results" / f"{role}-{n}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            rows.append({"endpoint": n, "error": f"{type(e).__name__}: {str(e)[:120]}"})
        print(f"{n}: {rows[-1]}", flush=True)
    head = ["endpoint", "n", *COLS, "p50_ms", "p95_ms", "usd_turn", "fallas", "r429", "wall_s"]
    md = [f"# Comparación de endpoints FM · rol `{role}` · {time.strftime('%Y-%m-%d %H:%M')}", "",
          "Mismo harness (`eval/run_eval.py`), mismos casos, `temperature=0`. Elección: mayor `paired_accuracy`, menor `fp_action_rate`, luego p95 y costo.", "",
          "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        md.append("| " + " | ".join(str(r.get(k, r.get("error", "—") if k == "n" else "—")) for k in head) + " |")
    out = ROOT / "eval" / "models.md"
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n" + "\n".join(md[4:]) + f"\n→ {out}")


if __name__ == "__main__":
    main()
