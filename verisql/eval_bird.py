import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import asyncio
import time
from tqdm import tqdm
from verisql.eval_utils import CheckpointManager, MetricsCalculator

# Ensure repo root on sys.path when running as a script
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from verisql.main import run_verisql
from verisql.agents.nodes import create_llm
from verisql.config import LLM_PROVIDER, SPEC_MODEL, SQL_MODEL
from verisql.artifacts import resolve_output_path, to_repo_relative
from verisql.run_metadata import (
    append_run_index,
    build_run_name,
    create_run_metadata,
    finalize_run_metadata,
)
from verisql.utils.llm_usage import (
    empty_usage_summary,
    make_usage_event,
    merge_usage_summaries,
)
from verisql.utils.sql_safety import validate_read_only_sql


def run_raw_llm(query: str, schema_info: dict) -> Tuple[str, Dict[str, Any]]:
    """Run a zero-shot raw LLM baseline without VeriSQL's verification and repair."""
    llm = create_llm(SQL_MODEL)

    # Format schema nicely
    schema_str = []
    for table, cols in schema_info.get("tables", {}).items():
        col_strs = [c["name"] for c in cols]
        schema_str.append(f"CREATE TABLE {table} ({', '.join(col_strs)});")

    schema_text = "\n".join(schema_str)

    prompt = f"""You are a SQLite expert. Generate a correct SQLite SQL query for the following natural language question based on the database schema.

Schema:
{schema_text}

Question:
{query}

Return ONLY the raw SQL query. Do NOT wrap it in markdown code blocks like ```sql ... ```. Do NOT explain your answer."""

    response = llm.invoke(prompt)
    sql = response.content.replace("```sql", "").replace("```", "").strip()
    llm_usage = merge_usage_summaries(
        empty_usage_summary(),
        make_usage_event(
            response,
            stage="raw_llm",
            model=SQL_MODEL,
            provider=LLM_PROVIDER,
        ),
    )
    return sql, llm_usage


def load_json(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _quote_sqlite_ident(name: str) -> str:
    """Quote a SQLite identifier (table/column) with double quotes."""
    # Escape embedded double-quotes by doubling them.
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def load_schema_from_sqlite(db_path: Path) -> Dict[str, Any]:
    """Extract schema_info in the same shape used by VeriSQL."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    schema_info: Dict[str, Any] = {"tables": {}}
    for (table_name,) in tables:
        if table_name.startswith("sqlite_"):
            continue
        # Table names may be reserved keywords (e.g., "order") or contain spaces.
        cursor.execute(f"PRAGMA table_info({_quote_sqlite_ident(table_name)})")
        columns = cursor.fetchall()
        col_info = []
        for col in columns:
            col_id, name, dtype, not_null, default, pk = col
            col_info.append({"name": name, "type": dtype, "primary_key": bool(pk)})
        schema_info["tables"][table_name] = col_info
    conn.close()
    return schema_info


def load_bird_descriptions(schema_info: Dict[str, Any], db_dir: Path) -> None:
    """Load BIRD database_description/*.csv if present (optional)."""
    desc_dir = db_dir / "database_description"
    if not desc_dir.exists():
        return
    schema_info.setdefault("descriptions", {})
    for csv_file in desc_dir.glob("*.csv"):
        table_name = csv_file.stem
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                schema_info["descriptions"][table_name] = list(reader)
        except Exception:
            # Non-fatal: descriptions are auxiliary.
            continue


def execute_sql(db_path: Path, sql: str) -> Tuple[bool, str, List[Tuple[Any, ...]]]:
    is_safe, safety_error = validate_read_only_sql(sql)
    if not is_safe:
        return False, safety_error, []

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return True, "", rows
    except Exception as e:
        return False, str(e), []


def _norm_cell(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float):
        return round(v, 6)
    return v


def normalize_rows(rows: Iterable[Tuple[Any, ...]]) -> List[Tuple[Any, ...]]:
    return [tuple(_norm_cell(v) for v in r) for r in rows]


def result_equal(
    gold_rows: List[Tuple[Any, ...]], pred_rows: List[Tuple[Any, ...]]
) -> bool:
    """Order-insensitive multiset equality (works for most BIRD cases)."""
    gold_n = normalize_rows(gold_rows)
    pred_n = normalize_rows(pred_rows)
    return Counter(gold_n) == Counter(pred_n)


def run_single(
    item: dict,
    db_path: Path,
    schema_info: Dict[str, Any],
    pred_source: str,
    ablation_mode: str = "none",
) -> Dict[str, Any]:
    question = item["question"]
    gold_sql = item.get("SQL") or item.get("sql") or ""

    if pred_source == "gold":
        pred_sql = gold_sql
        verisql_out = {
            "sql": pred_sql,
            "verified": None,
            "repair_iterations": 0,
            "ltl_formula": None,
            "llm_usage": empty_usage_summary(),
            "errors": [],
            "execution_status": "skipped",
        }
    elif pred_source == "raw_llm":
        evidence = item.get("evidence", "")
        query_with_hint = f"{question}\n\nHint: {evidence}" if evidence else question

        # Zero-shot raw LLM baseline
        try:
            pred_sql, llm_usage = run_raw_llm(query_with_hint, schema_info)
            verisql_out = {
                "sql": pred_sql,
                "verified": None,
                "repair_iterations": 0,
                "ltl_formula": None,
                "llm_usage": llm_usage,
                "errors": [],
                "execution_status": "raw_llm",
            }
        except Exception as e:
            pred_sql = ""
            verisql_out = {
                "sql": "",
                "verified": False,
                "repair_iterations": 0,
                "llm_usage": empty_usage_summary(),
                "errors": [str(e)],
                "execution_status": "failed",
            }
    else:
        # Append BIRD evidence as a hint so the LLM can resolve semantic mappings
        # e.g., "Youth Authority Facilities (CEA) refers to SOC = 11"
        evidence = item.get("evidence", "")
        query_with_hint = f"{question}\n\nHint: {evidence}" if evidence else question
        verisql_out = run_verisql(
            query=query_with_hint,
            schema_info=schema_info,
            db_path=str(db_path),
            verbose=False,
            ablation_mode=ablation_mode,
        )
        pred_sql = verisql_out.get("sql") or ""

    # Always attempt to execute both (EX proxy)
    gold_ok, gold_err, gold_rows = execute_sql(db_path, gold_sql)
    pred_ok, pred_err, pred_rows = (
        execute_sql(db_path, pred_sql) if pred_sql else (False, "empty SQL", [])
    )

    ex = 1 if (gold_ok and pred_ok and result_equal(gold_rows, pred_rows)) else 0

    return {
        "question_id": item.get("question_id"),
        "db_id": item.get("db_id"),
        "difficulty": item.get("difficulty"),
        "question": question,
        "evidence": item.get("evidence", ""),
        "gold_sql": gold_sql,
        "pred_sql": pred_sql,
        "verisql": verisql_out,
        "gold_exec_ok": gold_ok,
        "gold_exec_err": gold_err,
        "pred_exec_ok": pred_ok,
        "pred_exec_err": pred_err,
        "ex": ex,
    }


def safely_run_single(item, db_path, schema_info, pred_source, ablation_mode="none"):
    start = time.time()
    try:
        res = run_single(item, db_path, schema_info, pred_source, ablation_mode)
    except Exception as e:
        res = {
            "question_id": item.get("question_id"),
            "db_id": item.get("db_id"),
            "error": str(e),
            "ex": 0,
            "pred_exec_ok": False,
        }
    res["latency"] = time.time() - start
    return res


async def eval_concurrently(
    data,
    db_root,
    pred_source,
    concurrency,
    checkpoint_mgr,
    run_metadata,
    ablation_mode="none",
):
    sem = asyncio.Semaphore(concurrency)

    async def process(item):
        async with sem:
            db_id = item["db_id"]
            db_dir = Path(db_root) / db_id
            db_path = db_dir / f"{db_id}.sqlite"

            if not db_path.exists():
                res = {
                    "question_id": item.get("question_id"),
                    "db_id": db_id,
                    "error": f"missing db file: {db_path}",
                    "ex": 0,
                    "pred_exec_ok": False,
                }
            else:
                # Load schema synchronously (fast enough)
                schema_info = load_schema_from_sqlite(db_path)
                load_bird_descriptions(schema_info, db_dir)

                # Execute long-running agent logic in thread pool
                res = await asyncio.to_thread(
                    safely_run_single,
                    item,
                    db_path,
                    schema_info,
                    pred_source,
                    ablation_mode,
                )

            res["run_id"] = run_metadata["run_id"]
            res["run_name"] = run_metadata["run_name"]
            checkpoint_mgr.append_result(res)
            return res

    tasks = [asyncio.create_task(process(item)) for item in data]

    for _ in tqdm(
        asyncio.as_completed(tasks), total=len(data), desc="Evaluating Concurrent"
    ):
        await _


def main():
    parser = argparse.ArgumentParser(description="VeriSQL BIRD Evaluation")
    parser.add_argument(
        "--data",
        type=str,
        default="verisql/DataBase/Bird/dev_20240627/dev_tied_append.json",
    )
    parser.add_argument(
        "--db-root",
        type=str,
        default="verisql/DataBase/Bird/dev_20240627/dev_databases",
    )
    parser.add_argument(
        "--limit", type=int, default=10000, help="Limit number of questions"
    )
    parser.add_argument(
        "--offset", type=int, default=0, help="Skip the first N questions"
    )
    parser.add_argument(
        "--db-id", type=str, default=None, help="Only evaluate a specific db_id"
    )
    parser.add_argument(
        "--pred-source",
        type=str,
        choices=["agent", "gold", "raw_llm"],
        default="agent",
        help="Use agent (VeriSQL), gold SQL, or raw_llm (pure zero-shot LLM without repair)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional output file name. If omitted, a stable run name is generated under paper_data/runs/",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default=None,
        help="Optional stable run name used for the output stem and run index.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=5, help="Number of concurrent validations"
    )
    parser.add_argument(
        "--ablation",
        type=str,
        choices=["none", "no_dynamic", "no_repair"],
        default="none",
        help="Ablation logic skip ('none', 'no_dynamic', 'no_repair')",
    )
    args = parser.parse_args()

    data_path = Path(args.data)
    db_root = Path(args.db_root)
    if not data_path.exists():
        raise FileNotFoundError(f"BIRD data not found: {data_path}")
    if not db_root.exists():
        raise FileNotFoundError(f"BIRD db root not found: {db_root}")

    data = load_json(data_path)
    if args.db_id:
        data = [x for x in data if x.get("db_id") == args.db_id]
    if args.offset:
        data = data[args.offset :]
    data = data[: args.limit]
    run_name = args.run_name or (
        Path(args.output).stem
        if args.output
        else build_run_name(
            study="bird",
            pred_source=args.pred_source,
            ablation_mode=args.ablation,
            data_path=data_path,
            db_id=args.db_id,
            limit=args.limit,
            offset=args.offset,
        )
    )
    output_name = args.output or f"{run_name}.jsonl"
    output_path = resolve_output_path(output_name, "runs", f"{run_name}.jsonl")
    summary_path = output_path.with_name(f"{output_path.stem}_summary.json")
    run_metadata = create_run_metadata(
        study="bird",
        run_name=run_name,
        output_path=output_path,
        summary_path=summary_path,
        input_path=data_path,
        pred_source=args.pred_source,
        ablation_mode=args.ablation,
        db_id=args.db_id,
        limit=args.limit,
        offset=args.offset,
        concurrency=args.concurrency,
        total_candidates=len(data),
    )

    # 1. Checkpointing Logic
    checkpoint_mgr = CheckpointManager(str(output_path))
    completed_ids = checkpoint_mgr.load_completed()
    to_do = [d for d in data if d.get("question_id") not in completed_ids]

    print(
        f"Dataset Size: {len(data)} | Checkpointed: {len(completed_ids)} | Remaining to run: {len(to_do)}"
    )

    # 2. Async Concurrent Execution
    if to_do:
        asyncio.run(
            eval_concurrently(
                to_do,
                db_root,
                args.pred_source,
                args.concurrency,
                checkpoint_mgr,
                run_metadata,
                args.ablation,
            )
        )

    # 3. Read all lines to aggregate metrics
    all_results = []
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    all_results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    metrics = MetricsCalculator.compute(all_results)
    metrics["run_id"] = run_metadata["run_id"]
    metrics["run_name"] = run_metadata["run_name"]
    metrics["provider"] = run_metadata["provider"]
    metrics["sql_model"] = run_metadata["sql_model"]
    metrics["spec_model"] = run_metadata["spec_model"]
    metrics["ablation_mode"] = args.ablation
    metrics["pred_source"] = args.pred_source
    metrics["data"] = str(data_path)
    metrics["output"] = to_repo_relative(output_path)

    # 4. Dump Summary
    finalized_metadata = finalize_run_metadata(
        run_metadata, completed_questions=len(all_results), metrics=metrics
    )

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {"run": finalized_metadata, "metrics": metrics},
            f,
            ensure_ascii=False,
            indent=2,
        )

    append_run_index(finalized_metadata)

    print("\nEvaluation Complete:")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"Run ID: {run_metadata['run_id']}")
    print(f"Run file: {to_repo_relative(output_path)}")
    print(f"Summary: {to_repo_relative(summary_path)}")


if __name__ == "__main__":
    main()
