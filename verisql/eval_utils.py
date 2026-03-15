import json
from pathlib import Path
from typing import List, Dict, Any, Set


class CheckpointManager:
    def __init__(self, jsonl_path: str):
        self.jsonl_path = Path(jsonl_path)
        self.completed_ids: Set[int] = set()

    def load_completed(self) -> Set[int]:
        self.completed_ids = set()
        if not self.jsonl_path.exists():
            return set()
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if "question_id" in data:
                        self.completed_ids.add(data["question_id"])
                except json.JSONDecodeError:
                    continue
        return self.completed_ids

    def append_result(self, result: Dict[str, Any]):
        out_str = json.dumps(result, ensure_ascii=False)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(out_str + "\n")


class MetricsCalculator:
    @staticmethod
    def compute(results: List[Dict[str, Any]]) -> Dict[str, float]:
        total = len(results)
        if total == 0:
            return {
                "total": 0,
                "ex_rate": 0.0,
                "svr": 0.0,
                "caa": 0.0,
                "avg_latency": 0.0,
            }

        ex = sum(1 for r in results if r.get("ex") == 1)

        # SVR (Specification Violation Rate): violated rules but SQL executed / total
        # Here we define a proxy for SVR: execution was ok, but verified was False.
        svr_count = sum(
            1
            for r in results
            if r.get("pred_exec_ok")
            and isinstance(r.get("verisql"), dict)
            and r["verisql"].get("verified") is False
        )

        # CAA (Combined Accuracy): EX == 1 AND verified == True
        caa_count = sum(
            1
            for r in results
            if r.get("ex") == 1
            and isinstance(r.get("verisql"), dict)
            and r["verisql"].get("verified") is True
        )

        usage_totals = {
            "call_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "priced_call_count": 0,
            "usage_available_call_count": 0,
        }
        usage_tracked_results = 0
        for result in results:
            verisql = result.get("verisql")
            if not isinstance(verisql, dict):
                continue
            llm_usage = verisql.get("llm_usage")
            if not isinstance(llm_usage, dict):
                continue
            totals = llm_usage.get("totals")
            if not isinstance(totals, dict):
                continue
            if int(totals.get("call_count", 0)) <= 0:
                continue
            usage_tracked_results += 1
            for key in usage_totals:
                usage_totals[key] += totals.get(key, 0)

        return {
            "total": total,
            "ex_rate": ex / total,
            "svr": svr_count / total,
            "caa": caa_count / total,
            "avg_latency": sum(r.get("latency", 0) for r in results) / total,
            "usage_tracked_results": usage_tracked_results,
            "llm_call_count": int(usage_totals["call_count"]),
            "total_prompt_tokens": int(usage_totals["prompt_tokens"]),
            "total_completion_tokens": int(usage_totals["completion_tokens"]),
            "total_tokens": int(usage_totals["total_tokens"]),
            "avg_total_tokens": (
                usage_totals["total_tokens"] / usage_tracked_results
                if usage_tracked_results
                else 0.0
            ),
            "total_estimated_cost_usd": round(
                float(usage_totals["estimated_cost_usd"]), 8
            ),
            "avg_estimated_cost_usd": (
                round(
                    float(usage_totals["estimated_cost_usd"]) / usage_tracked_results,
                    8,
                )
                if usage_tracked_results
                else 0.0
            ),
        }
