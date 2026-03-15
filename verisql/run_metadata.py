import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from verisql.artifacts import ARTIFACT_ROOT, REPO_ROOT, to_repo_relative
from verisql.config import LLM_PROVIDER, SPEC_MODEL, SQL_MODEL


RUN_INDEX_PATH = ARTIFACT_ROOT / "run_index.jsonl"


def slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "unnamed"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def compact_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def get_git_revision() -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip() or None
    except Exception:
        return None


def is_git_dirty() -> Optional[bool]:
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(proc.stdout.strip())
    except Exception:
        return None


def build_dataset_slice_label(
    data_path: Path, db_id: Optional[str], limit: int, offset: int
) -> str:
    db_part = f"db-{slugify(db_id)}" if db_id else "db-all"
    return f"{slugify(data_path.stem)}_{db_part}_l{limit}_o{offset}"


def build_run_name(
    *,
    study: str,
    pred_source: str,
    ablation_mode: str,
    data_path: Path,
    db_id: Optional[str],
    limit: int,
    offset: int,
    provider: str = LLM_PROVIDER,
    sql_model: str = SQL_MODEL,
    spec_model: str = SPEC_MODEL,
) -> str:
    slice_label = build_dataset_slice_label(data_path, db_id, limit, offset)
    parts = [
        slugify(study),
        slugify(pred_source),
        slugify(provider),
        f"sql-{slugify(sql_model)}",
    ]
    if pred_source == "agent":
        parts.append(f"spec-{slugify(spec_model)}")
        parts.append(f"abl-{slugify(ablation_mode)}")
    parts.append(slice_label)
    parts.append(compact_timestamp())
    return "_".join(parts)


def create_run_metadata(
    *,
    study: str,
    run_name: str,
    output_path: Path,
    summary_path: Path,
    input_path: Path,
    pred_source: str,
    ablation_mode: str,
    db_id: Optional[str],
    limit: int,
    offset: int,
    concurrency: int,
    total_candidates: int,
    provider: str = LLM_PROVIDER,
    sql_model: str = SQL_MODEL,
    spec_model: str = SPEC_MODEL,
) -> Dict[str, Any]:
    timestamp = now_iso()
    return {
        "run_id": run_name,
        "run_name": run_name,
        "study": study,
        "created_at": timestamp,
        "completed_at": None,
        "provider": provider,
        "sql_model": sql_model,
        "spec_model": spec_model,
        "pred_source": pred_source,
        "ablation_mode": ablation_mode,
        "dataset": to_repo_relative(input_path),
        "dataset_slice": build_dataset_slice_label(input_path, db_id, limit, offset),
        "db_id": db_id,
        "limit": limit,
        "offset": offset,
        "concurrency": concurrency,
        "candidate_questions": total_candidates,
        "output": to_repo_relative(output_path),
        "summary": to_repo_relative(summary_path),
        "git_revision": get_git_revision(),
        "git_dirty": is_git_dirty(),
    }


def finalize_run_metadata(
    metadata: Dict[str, Any], *, completed_questions: int, metrics: Dict[str, Any]
) -> Dict[str, Any]:
    finalized = dict(metadata)
    finalized["completed_at"] = now_iso()
    finalized["completed_questions"] = completed_questions
    finalized["metrics"] = metrics
    return finalized


def append_run_index(entry: Dict[str, Any], index_path: Path = RUN_INDEX_PATH) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    existing_entries = []
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("run_id") == entry.get("run_id"):
                    continue
                existing_entries.append(item)

    existing_entries.append(entry)
    with open(index_path, "w", encoding="utf-8") as f:
        for item in existing_entries:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
