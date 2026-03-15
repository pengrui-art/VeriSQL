import json
import argparse
import collections

from verisql.artifacts import resolve_input_path, resolve_output_path, to_repo_relative


def load_jsonl(filepath):
    data = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            data[item["question_id"]] = item
    return data


def find_destructive_repairs(
    agent_file, norepair_file, output_file="destructive_repairs_report.md"
):
    agent_path = resolve_input_path(agent_file, "runs")
    norepair_path = resolve_input_path(norepair_file, "runs")
    output_path = resolve_output_path(
        output_file, "reports", "destructive_repairs_report.md"
    )

    print(f"Loading Full Agent run: {to_repo_relative(agent_path)}")
    agent_data = load_jsonl(agent_path)

    print(f"Loading No-Repair run: {to_repo_relative(norepair_path)}")
    norepair_data = load_jsonl(norepair_path)

    destructive_cases = []
    beneficial_cases = []

    # Analyze overlap
    for q_id, norepair_item in norepair_data.items():
        if q_id not in agent_data:
            continue

        agent_item = agent_data[q_id]

        ex_norepair = norepair_item.get("ex", 0)
        ex_agent = agent_item.get("ex", 0)

        # Destructive Repair: It was correct before repair, but incorrect after!
        if ex_norepair == 1 and ex_agent == 0:
            destructive_cases.append((norepair_item, agent_item))

        # Beneficial Repair: It was wrong initially, but fixed beautifully!
        elif ex_norepair == 0 and ex_agent == 1:
            beneficial_cases.append((norepair_item, agent_item))

    print(
        f"Found {len(destructive_cases)} destructive repairs (False Positives in verification)"
    )
    print(f"Found {len(beneficial_cases)} beneficial repairs (True Corrections)")

    # Generate Markdown Report
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"# VeriSQL Repair Impact Analysis\n\n")
        out.write(
            f"This report compares the initial SQL generation (No Repair) vs the final SQL after the Verification & Repair loop.\n\n"
        )

        out.write(f"## Destructive Repairs ({len(destructive_cases)} cases)\n")
        out.write(
            f"*These are cases where the initial SQL was **CORRECT** (EX=1), but the Verifier falsely flagged it and the Repair module made it **INCORRECT** (EX=0).*\n\n"
        )

        for norepair_item, agent_item in destructive_cases:
            q_id = norepair_item["question_id"]
            db_id = norepair_item["db_id"]

            # The initial correct SQL
            initial_sql = norepair_item.get("pred_sql", "")

            # The broken SQL and the errors that drove it
            final_sql = agent_item.get("pred_sql", "")
            verisql_log = agent_item.get("verisql", {})
            errors = verisql_log.get("errors", [])
            iterations = verisql_log.get("repair_iterations", "unknown")

            out.write(f"### Q{q_id} ({db_id})\n")
            out.write(f"**Question:** {norepair_item['question']}\n\n")

            out.write(
                f"**1. Initial Correct SQL (No Repair)**:\n```sql\n{initial_sql}\n```\n\n"
            )

            out.write(f"**2. Verifier Errors Triggered (The False Positives)**:\n")
            for err in errors:
                out.write(f"- `{err}`\n")
            out.write(f"\n")

            out.write(
                f"**3. Final Broken SQL (After {iterations} iterations)**:\n```sql\n{final_sql}\n```\n\n"
            )
            out.write(f"---\n")

        out.write(f"## Beneficial Repairs ({len(beneficial_cases)} cases)\n")
        out.write(
            f"*These are cases where the initial SQL was **INCORRECT** (EX=0), but the Repair module successfully fixed it to **CORRECT** (EX=1).*\n\n"
        )

        for norepair_item, agent_item in beneficial_cases:
            q_id = norepair_item["question_id"]
            db_id = norepair_item["db_id"]

            initial_sql = norepair_item.get("pred_sql", "")
            final_sql = agent_item.get("pred_sql", "")
            errors = agent_item.get("verisql", {}).get("errors", [])

            out.write(f"### Q{q_id} ({db_id})\n")
            out.write(f"**Question:** {norepair_item['question']}\n\n")
            out.write(f"**Initial Buggy SQL**:\n```sql\n{initial_sql}\n```\n")
            out.write(f"**Fixed SQL**:\n```sql\n{final_sql}\n```\n")
            out.write(f"---\n")

    print(f"Report generated successfully: {to_repo_relative(output_path)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Find Destructive Repairs by comparing two eval runs."
    )
    parser.add_argument(
        "--agent",
        type=str,
        default="result_verisql_qwen.jsonl",
        help="Full pipeline output. Relative names are resolved under paper_data/runs/",
    )
    parser.add_argument(
        "--no-repair",
        type=str,
        default="result_norepair_qwen.jsonl",
        help="No-repair output. Relative names are resolved under paper_data/runs/",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="destructive_repairs_report.md",
        help="Output markdown file. Relative names are written under paper_data/reports/",
    )

    args = parser.parse_args()
    find_destructive_repairs(args.agent, args.no_repair, args.output)
