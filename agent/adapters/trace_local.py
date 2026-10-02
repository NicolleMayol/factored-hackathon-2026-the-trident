"""Trazas locales: spans como logs JSON y filas de ops.agent_turns en data/mock/ops_agent_turns.jsonl. Misma interfaz que trace_mlflow."""
from __future__ import annotations
import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class TraceLocal:
    def __init__(self, settings):
        self.out = Path(settings.mock_dir) / "ops_agent_turns.jsonl"
        self.spans: list[dict[str, Any]] = []

    @contextmanager
    def span(self, name: str, **attrs: Any):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.spans.append({"name": name, "ms": round((time.perf_counter() - t0) * 1000, 1), **attrs})

    def log_turn(self, row: dict[str, Any]) -> None:
        with open(self.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
