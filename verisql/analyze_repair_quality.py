import argparse
import collections
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from verisql.artifacts import resolve_input_path, resolve_output_path, to_repo_relative


def load_jsonl_by_question(path: Path) -> Dict[int, Dict[str, Any]]:
    data: Dict[int, Dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            qid = item.get("question_id")
            if qid is not None:
                data[qid] = item
    return data


def extract_patch_actions(verisql_log: Dict[str, Any]) -> Tuple[set[str], collections.Counter]:
    unique_actions: set[str] = set()
    occurrences: collections.Counter = collections.Counter()

    repair_history = verisql_log.get("repair_history", [])
    for repair in repair_history:
        for fault in repair.get("fault_localizations", []):
            for action in fault.get("patch_actions", []):
                action_type = action.get("action_type") or "UNKNOWN"
                unique_actions.add(action_type)
                occurrences[action_type] += 1

    return unique_actions, occurrences


def compare_repair_runs(
    agent_data: Dict[int, Dict[str, Any]], norepair_data: Dict[int, Dict[str, Any]]
) -> Dict[str, Any]:
    patch_action_stats: Dict[str, Dict[str, Any]] = collections.defaultdict(
        lambda: {
            "question_count": 0,
            "occurrences": 0,
            "beneficial": 0,
            "destructive": 0,
            "neutral": 0,
            "final_ex_success": 0,
        }
    )
    beneficial_cases = []
    destructive_cases = []
    neutral_cases = []
    overlap = 0
    repaired_cases = 0

    for qid, agent_item in agent_data.items():
        baseline_item = norepair_data.get(qid)
        if baseline_item is None:
            continue
        overlap += 1

        agent_log = agent_item.get("verisql", {}) if isinstance(agent_item.get("verisql"), dict) else {}
        repair_iterations = int(agent_log.get("repair_iterations", 0) or 0)
        unique_actions, occurrences = extract_patch_actions(agent_log)
        if repair_iterations <= 0 and not unique_actions:
            continue

        repaired_cases += 1
        baseline_ex = int(baseline_item.get("ex", 0) or 0)
        agent_ex = int(agent_item.get("ex", 0) or 0)

        outcome = "neutral"
        if agent_ex > baseline_ex:
            outcome = "beneficial"
        elif agent_ex < baseline_ex:
            outcome = "destructive"

        case_record = {
            "question_id": qid,
            "db_id": agent_item.get("db_id"),
            "question": agent_item.get("question"),
            "baseline_ex": baseline_ex,
            "agent_ex": agent_ex,
            "repair_iterations": repair_iterations,
            "patch_actions": sorted(unique_actions),
            "baseline_sql": baseline_item.get("pred_sql", ""),
            "agent_sql": agent_item.get("pred_sql", ""),
        }
        if outcome == "beneficial":
            beneficial_cases.append(case_record)
        elif outcome == "destructive":
            destructive_cases.append(case_record)
        else:
            neutral_cases.append(case_record)

        for action_type, count in occurrences.items():
            patch_action_stats[action_type]["occurrences"] += count
        for action_type in unique_actions:
            stats = patch_action_stats[action_type]
            stats["question_count"] += 1
            stats[outcome] += 1
            if agent_ex == 1:
                stats["final_ex_success"] += 1

    summarized_patch_actions = {}
    for action_type, stats in patch_action_stats.items():
        question_count = stats["question_count"] or 1
        summarized_patch_actions[action_type] = {
            **stats,
            "beneficial_rate": round(stats["beneficial"] / question_count, 4),
            "destructive_rate": round(stats["destructive"] / question_count, 4),
            "final_ex_success_rate": round(stats["final_ex_success"] / question_count, 4),
        }

    return {
        "overlap_questions": overlap,
        "repaired_cases": repaired_cases,
        "beneficial_repairs": len(beneficial_cases),
        "destructive_repairs": len(destructive_cases),
        "neutral_repairs": len(neutral_cases),
        "beneficial_cases": beneficial_cases,
        "destructive_cases": destructive_cases,
        "neutral_cases": neutral_cases,
        "patch_action_stats": dict(sorted(summarized_patch_actions.items())),
    }


def write_repair_quality_report(
    analysis: Dict[str, Any],
    *,
    agent_path: Path,
    norepair_path: Path,
    report_path: Path,
    summary_path: Path,
) -> None:
    with open(report_path, "w", encoding="utf-8") as out:
        out.write("# VeriSQL Repair Quality Report\n\n")
        out.write(f"- Agent run: `{to_repo_relative(agent_path)}`\n")
        out.write(f"- No-repair run: `{to_repo_relative(norepair_path)}`\n")
        out.write(f"- Overlap questions: {analysis['overlap_questions']}\n")
        out.write(f"- Repaired cases: {analysis['repaired_cases']}\n")
        out.write(f"- Beneficial repairs: {analysis['beneficial_repairs']}\n")
        out.write(f"- Destructive repairs: {analysis['destructive_repairs']}\n")
        out.write(f"- Neutral repairs: {analysis['neutral_repairs']}\n\n")

        out.write("## Patch Action Summary\n\n")
        out.write(
            "| Action | Questions | Occurrences | Beneficial | Destructive | Neutral | Success Rate |\n"
        )
        out.write(
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        )
        for action_type, stats in analysis["patch_action_stats"].items():
            out.write(
                f"| {action_type} | {stats['question_count']} | {stats['occurrences']} | "
                f"{stats['beneficial']} | {stats['destructive']} | {stats['neutral']} | "
                f"{stats['beneficial_rate']:.4f} |\n"
            )
        out.write("\n")

        def write_cases(title: str, cases: Iterable[Dict[str, Any]]) -> None:
            cases = list(cases)
            out.write(f"## {title}\n\n")
            for case in cases:
                out.write(
                    f"### Q{case['question_id']} ({case['db_id']})\n"
                    f"**Question:** {case['question']}\n\n"
                    f"**Patch Actions:** {', '.join(case['patch_actions']) or 'N/A'}\n\n"
                    f"**No-Repair SQL**\n```sql\n{case['baseline_sql']}\n```\n\n"
                    f"**Final SQL**\n```sql\n{case['agent_sql']}\n```\n\n"
                )
            if not cases:
                out.write("_None._\n\n")

        write_cases("Beneficial Repairs", analysis["beneficial_cases"][:10])
        write_cases("Destructive Repairs", analysis["destructive_cases"][:10])

    with open(summary_path, "w", encoding="utf-8") as out:
        json.dump(analysis, out, ensure_ascii=False, indent=2)


def analyze_repair_quality(
    agent_file: str,
    norepair_file: str,
    output_file: str = "repair_quality_report.md",
    summary_file: str | None = None,
) -> None:
    agent_path = resolve_input_path(agent_file, "runs")
    norepair_path = resolve_input_path(norepair_file, "runs")
    report_path = resolve_output_path(output_file, "reports", "repair_quality_report.md")
    summary_name = summary_file or f"{report_path.stem}_summary.json"
    summary_path = resolve_output_path(summary_name, "reports", summary_name)

    analysis = compare_repair_runs(
        load_jsonl_by_question(agent_path),
        load_jsonl_by_question(norepair_path),
    )
    write_repair_quality_report(
        analysis,
        agent_path=agent_path,
        norepair_path=norepair_path,
        report_path=report_path,
        summary_path=summary_path,
    )
    print(f"Repair quality report: {to_repo_relative(report_path)}")
    print(f"Repair quality summary: {to_repo_relative(summary_path)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Quantify VeriSQL repair quality against the no-repair baseline."
    )
    parser.add_argument(
        "--agent",
        type=str,
        default="result_verisql_qwen.jsonl",
        help="Full VeriSQL run. Relative names are resolved under paper_data/runs/",
    )
    parser.add_argument(
        "--no-repair",
        type=str,
        default="result_norepair_qwen.jsonl",
        help="No-repair ablation run. Relative names are resolved under paper_data/runs/",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="repair_quality_report.md",
        help="Markdown report. Relative names are written under paper_data/reports/",
    )
    parser.add_argument(
        "--summary-output",
        type=str,
        default=None,
        help="Optional JSON summary file. Relative names are written under paper_data/reports/",
    )
    args = parser.parse_args()
    analyze_repair_quality(
        args.agent,
        args.no_repair,
        args.output,
        args.summary_output,
    )
