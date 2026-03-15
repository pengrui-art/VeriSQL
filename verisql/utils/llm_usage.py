import json
import os
from copy import deepcopy
from typing import Any, Dict, Optional


DEFAULT_MODEL_PRICING_PER_1K_USD: Dict[str, Dict[str, float]] = {
    # Best-effort defaults. Override with MODEL_PRICING_JSON for paper-grade accounting.
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "deepseek-chat": {"input": 0.00027, "output": 0.0011},
    "qwen-plus": {"input": 0.0008, "output": 0.002},
    "qwen-turbo": {"input": 0.0003, "output": 0.0006},
    "qwen-max": {"input": 0.0024, "output": 0.0072},
}


def empty_usage_summary() -> Dict[str, Any]:
    return {
        "events": [],
        "totals": {
            "call_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "priced_call_count": 0,
            "usage_available_call_count": 0,
        },
    }


def _load_pricing_table() -> Dict[str, Dict[str, float]]:
    pricing = deepcopy(DEFAULT_MODEL_PRICING_PER_1K_USD)
    raw_override = os.getenv("MODEL_PRICING_JSON", "").strip()
    if not raw_override:
        return pricing

    try:
        override = json.loads(raw_override)
    except json.JSONDecodeError:
        return pricing

    for model, entry in override.items():
        if not isinstance(entry, dict):
            continue
        input_price = entry.get("input") or entry.get("input_per_1k_usd")
        output_price = entry.get("output") or entry.get("output_per_1k_usd")
        if input_price is None or output_price is None:
            continue
        pricing[model] = {"input": float(input_price), "output": float(output_price)}
    return pricing


MODEL_PRICING_PER_1K_USD = _load_pricing_table()


def extract_token_usage(response: Any) -> Dict[str, Any]:
    usage = getattr(response, "usage_metadata", None)
    if not usage and hasattr(response, "response_metadata"):
        metadata = getattr(response, "response_metadata", {}) or {}
        usage = metadata.get("token_usage") or metadata.get("usage") or {}
    usage = usage or {}

    prompt_tokens = (
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("input_token_count")
        or 0
    )
    completion_tokens = (
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("output_token_count")
        or 0
    )
    total_tokens = usage.get("total_tokens") or (prompt_tokens + completion_tokens)

    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "usage_available": bool(usage),
    }


def estimate_cost_usd(
    model: str, prompt_tokens: int, completion_tokens: int
) -> Optional[float]:
    pricing = MODEL_PRICING_PER_1K_USD.get(model)
    if not pricing:
        return None

    return round(
        (prompt_tokens / 1000.0) * pricing["input"]
        + (completion_tokens / 1000.0) * pricing["output"],
        8,
    )


def make_usage_event(
    response: Any,
    *,
    stage: str,
    model: str,
    provider: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usage = extract_token_usage(response)
    estimated_cost = estimate_cost_usd(
        model, usage["prompt_tokens"], usage["completion_tokens"]
    )
    event = {
        "stage": stage,
        "provider": provider,
        "model": model,
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "usage_available": usage["usage_available"],
        "estimated_cost_usd": estimated_cost,
    }
    if extra:
        event.update(extra)
    return event


def merge_usage_summaries(
    existing: Optional[Dict[str, Any]], event: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    merged = deepcopy(existing) if existing else empty_usage_summary()
    if not event:
        return merged

    merged.setdefault("events", []).append(event)
    totals = merged.setdefault("totals", {})
    totals["call_count"] = int(totals.get("call_count", 0)) + 1
    totals["prompt_tokens"] = int(totals.get("prompt_tokens", 0)) + int(
        event.get("prompt_tokens", 0)
    )
    totals["completion_tokens"] = int(totals.get("completion_tokens", 0)) + int(
        event.get("completion_tokens", 0)
    )
    totals["total_tokens"] = int(totals.get("total_tokens", 0)) + int(
        event.get("total_tokens", 0)
    )
    totals["usage_available_call_count"] = int(
        totals.get("usage_available_call_count", 0)
    ) + int(bool(event.get("usage_available")))

    estimated_cost = event.get("estimated_cost_usd")
    if estimated_cost is not None:
        totals["estimated_cost_usd"] = round(
            float(totals.get("estimated_cost_usd", 0.0)) + float(estimated_cost), 8
        )
        totals["priced_call_count"] = int(totals.get("priced_call_count", 0)) + 1
    else:
        totals.setdefault("estimated_cost_usd", 0.0)
        totals.setdefault("priced_call_count", int(totals.get("priced_call_count", 0)))

    return merged
