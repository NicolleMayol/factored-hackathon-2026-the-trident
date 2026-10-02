"""Corre eval/cases.jsonl contra el agente y calcula la matriz de confusión de acción por idioma (eval/metrics.md).

    python eval/run_eval.py                 # mocks (AGENT_*=mock)
    python eval/run_eval.py --limit 20      # muestra
    AGENT_LLM=real python eval/run_eval.py  # it. 4: mismo harness con FM APIs

Escribe eval/results/latest.json y sale con 1 si una métrica queda bajo umbral (eval/metrics.py THRESHOLDS).
"""
from __future__ import annotations
import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.cli import USERS  # noqa: E402
from agent.handle import handle, runtime  # noqa: E402
from eval.metrics import check, metrics, render_confusion  # noqa: E402


def run(limit: int | None = None) -> dict:
    rt = runtime()
    _, deps, _ = rt
    cases = [json.loads(l) for l in open(ROOT / "eval" / "cases.jsonl", encoding="utf-8")]
    if limit:
        cases = cases[:limit]
    rows = []
    node_ms: dict[str, list[float]] = defaultdict(list)
    for c in cases:
        n0 = len(deps.trace.spans) if hasattr(deps.trace, "spans") else 0
        t0 = time.perf_counter()
        r = handle(c["message"], {**USERS[c["user"]], "expected_action": c["expected_action"]}, rt=rt)
        ms = (time.perf_counter() - t0) * 1000
        st = r["_state"]
        if hasattr(deps.trace, "spans"):
            for sp in deps.trace.spans[n0:]:
                node_ms[sp.get("tool") and f"tool:{sp['tool']}" or sp["name"]].append(sp["ms"])
        informed = bool(st.get("reason_code")) and (r["action"] != "escalate" or bool(r.get("case_id")))
        rows.append({**{k: c[k] for k in ("case_id", "category", "pair_id", "language", "expected_action", "message")}, "atlas": c.get("atlas"),
                     "action": r["action"], "escalate_reason": st.get("escalate_reason", "none"), "rules_fired": st.get("rules_fired", []),
                     "informed": informed, "verify_ok": bool(st.get("verify_ok", True)), "citations": len(r["citations"]),
                     "latency_ms": round(ms, 1), "cost_usd": r.get("cost_usd", 0.0)})
    by_lang = {lang: metrics([x for x in rows if x["language"] == lang]) for lang in sorted({x["language"] for x in rows})}
    allm = metrics(rows)
    lat = [x["latency_ms"] for x in rows]
    rep = {"ts": time.time(), "runtime": {"llm": getattr(deps.llm, "model_version", "?"), "embed": deps.embed.model_version},
           "all": allm, "by_language": by_lang,
           "groundedness": round(sum(x["verify_ok"] for x in rows if x["action"] == "answer") / max(1, sum(1 for x in rows if x["action"] == "answer")), 3),
           "latency_ms": {"p50": round(statistics.median(lat), 1), "p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1)},
           "node_ms_p50": {k: round(statistics.median(v), 1) for k, v in node_ms.items()},
           "cost_usd_per_turn": round(sum(x["cost_usd"] for x in rows) / len(rows), 5),
           "failures": [x for x in rows if not (x["action"] == x["expected_action"] or (x["expected_action"] in ("clarify", "escalate", "blocked", "reject") and x["action"] in ("clarify", "escalate", "blocked", "reject")))],
           "rows": rows}
    return rep


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int); ap.add_argument("--out", default=str(ROOT / "eval" / "results" / "latest.json"))
    a = ap.parse_args()
    rep = run(a.limit)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Eval · {rep['all']['n']} casos · llm={rep['runtime']['llm']} embed={rep['runtime']['embed']}")
    for lang, m in rep["by_language"].items():
        print(f"\n[{lang}] n={m['n']}\n" + render_confusion(m["confusion"]))
        print("  " + " · ".join(f"{k}={m[k]}" for k in ("act_accuracy", "abstain_accuracy", "paired_accuracy", "car", "ur", "irr", "fp_action_rate", "ivr", "exact_match")))
    m = rep["all"]
    print(f"\n[all] " + " · ".join(f"{k}={m[k]}" for k in ("act_accuracy", "abstain_accuracy", "paired_accuracy", "car", "ur", "irr", "fp_action_rate", "ivr", "exact_match")))
    print(f"  IVR por ATLAS: {m['ivr_by_atlas']} · escalate_reason: {m['escalate_reason']}")
    print(f"  groundedness={rep['groundedness']} · latencia p50/p95={rep['latency_ms']['p50']}/{rep['latency_ms']['p95']} ms · nodos p50={rep['node_ms_p50']} · costo/turno={rep['cost_usd_per_turn']} USD")
    for f in rep["failures"]:
        print(f"  FALLA {f['case_id']} [{f['category']}/{f['language']}] esperado={f['expected_action']} tomado={f['action']} reglas={f['rules_fired']} · {f['message'][:60]}")
    fails = check(m)
    print("\nUMBRALES: " + ("ok" if not fails else "; ".join(fails)))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
