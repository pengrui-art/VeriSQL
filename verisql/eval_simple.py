import argparse
import json
from pathlib import Path

from verisql.artifacts import resolve_output_path, to_repo_relative
from verisql.create_sample_db import create_sample_database
from verisql.eval_bird import load_json, load_schema_from_sqlite, safely_run_single
from verisql.eval_utils import CheckpointManager, MetricsCalculator
from verisql.run_metadata import (
    append_run_index,
    build_run_name,
    create_run_metadata,
    finalize_run_metadata,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPO_ROOT / "verisql" / "data" / "simple_queries.json"
DEFAULT_DB = REPO_ROOT / "paper_data" / "simple_regression" / "sample_store.sqlite"


def ensure_sample_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        create_sample_database(str(db_path))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simple-query non-regression evaluation on the sample_store fixture."
    )
    parser.add_argument("--data", type=str, default=str(DEFAULT_DATA))
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB))
    parser.add_argument(
        "--pred-source",
        type=str,
        choices=["agent", "gold", "raw_llm"],
        default="gold",
    )
    parser.add_argument(
        "--ablation",
        type=str,
        choices=["none", "no_dynamic", "no_repair"],
        default="none",
    )
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--run-name", type=str, default=None)
    args = parser.parse_args()

    data_path = Path(args.data)
    db_path = Path(args.db)
    ensure_sample_db(db_path)

    data = load_json(data_path)
    if args.offset:
        data = data[args.offset :]
    data = data[: args.limit]

    run_name = args.run_name or (
        Path(args.output).stem
        if args.output
        else build_run_name(
            study="simple_regression",
            pred_source=args.pred_source,
            ablation_mode=args.ablation,
            data_path=data_path,
            db_id="sample_store",
            limit=args.limit,
            offset=args.offset,
        )
    )
    output_name = args.output or f"{run_name}.jsonl"
    output_path = resolve_output_path(output_name, "runs", f"{run_name}.jsonl")
    summary_path = output_path.with_name(f"{output_path.stem}_summary.json")
    run_metadata = create_run_metadata(
        study="simple_regression",
        run_name=run_name,
        output_path=output_path,
        summary_path=summary_path,
        input_path=data_path,
        pred_source=args.pred_source,
        ablation_mode=args.ablation,
        db_id="sample_store",
        limit=args.limit,
        offset=args.offset,
        concurrency=1,
        total_candidates=len(data),
    )

    checkpoint_mgr = CheckpointManager(str(output_path))
    completed_ids = checkpoint_mgr.load_completed()
    pending = [item for item in data if item.get("question_id") not in completed_ids]

    schema_info = load_schema_from_sqlite(db_path)
    for item in pending:
        result = safely_run_single(
            item,
            db_path,
            schema_info,
            args.pred_source,
            args.ablation,
        )
        result["run_id"] = run_metadata["run_id"]
        result["run_name"] = run_metadata["run_name"]
        checkpoint_mgr.append_result(result)

    all_results = []
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_results.append(json.loads(line))

    metrics = MetricsCalculator.compute(all_results)
    metrics["run_id"] = run_metadata["run_id"]
    metrics["run_name"] = run_metadata["run_name"]
    metrics["pred_source"] = args.pred_source
    metrics["ablation_mode"] = args.ablation
    metrics["data"] = to_repo_relative(data_path)
    metrics["output"] = to_repo_relative(output_path)

    finalized_metadata = finalize_run_metadata(
        run_metadata,
        completed_questions=len(all_results),
        metrics=metrics,
    )
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {"run": finalized_metadata, "metrics": metrics},
            f,
            ensure_ascii=False,
            indent=2,
        )

    append_run_index(finalized_metadata)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"Run file: {to_repo_relative(output_path)}")
    print(f"Summary: {to_repo_relative(summary_path)}")


if __name__ == "__main__":
    main()
