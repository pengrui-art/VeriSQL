import json
import argparse
import collections

from verisql.artifacts import resolve_input_path, resolve_output_path, to_repo_relative


def analyze_failures(jsonl_file, output_file="failure_report.md"):
    input_path = resolve_input_path(jsonl_file, "runs")
    output_path = resolve_output_path(output_file, "reports", "failure_report.md")
    total = 0
    failures = 0

    # Categories
    exec_errors = collections.defaultdict(list)  # SQL Execution failed
    logic_errors = collections.defaultdict(list)  # SQL Executed but result wrong (ex=0)

    print(f"Loading {to_repo_relative(input_path)}...")

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            total += 1

            ex = data.get("ex", 0)
            pred_exec_ok = data.get("pred_exec_ok", False)
            pred_exec_err = data.get("pred_exec_err", "")

            if ex == 0:
                failures += 1
                item = {
                    "question_id": data.get("question_id"),
                    "db_id": data.get("db_id"),
                    "question": data.get("question"),
                    "gold": data.get("gold_sql"),
                    "pred": data.get("pred_sql"),
                    "err": pred_exec_err,
                }

                if not pred_exec_ok and pred_exec_err:
                    # Categorize the execution error
                    err_msg = str(pred_exec_err).lower()
                    if "no such column" in err_msg:
                        exec_errors["No such column (Schema mapping error)"].append(
                            item
                        )
                    elif "no such table" in err_msg:
                        exec_errors["No such table (Hallucination)"].append(item)
                    elif "ambiguous column" in err_msg:
                        exec_errors["Ambiguous column (JOIN issue)"].append(item)
                    elif "syntax error" in err_msg:
                        exec_errors["Syntax error"].append(item)
                    elif "group by" in err_msg or "aggregate" in err_msg.lower():
                        exec_errors["Aggregation/Group By error"].append(item)
                    else:
                        exec_errors["Other execution errors"].append(item)
                else:
                    # Executed OK, but wrong answer (Logic Error)
                    logic_errors[
                        "Logic mismatch (Wrong logical plan / missing conditions)"
                    ].append(item)

    # Generate Markdown Report
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"# VeriSQL Failure Taxonomy Report\n\n")
        out.write(f"**Source File:** `{to_repo_relative(input_path)}`\n")
        out.write(f"**Total Queried:** {total}\n")
        out.write(
            f"**Failed Queries:** {failures} (Success Rate: {(total-failures)/total*100:.2f}%)\n\n"
        )

        out.write(f"## 1. Execution Errors (Syntax & Schema Hallucinations)\n")
        out.write(
            f"These queries completely failed to run on the sandbox database.\n\n"
        )
        for cat, items in exec_errors.items():
            out.write(f"### {cat} ({len(items)} cases)\n")
            for i, item in enumerate(items[:3]):  # sample top 3 per category
                out.write(
                    f"- **Q{item['question_id']} ({item['db_id']})**: {item['question']}\n"
                )
                out.write(f"  - **Error String**: `{item['err']}`\n")
                out.write(f"  - **Pred SQL**: `{item['pred']}`\n")
            if len(items) > 3:
                out.write(f"- *... and {len(items)-3} more.*\n")
            out.write("\n")

        out.write(f"## 2. Logic Errors (Executed Success, but Ex==0)\n")
        out.write(
            f"These queries ran successfully, but the result set did not match the Gold SQL.\n\n"
        )
        for cat, items in logic_errors.items():
            out.write(f"### {cat} ({len(items)} cases)\n")
            # Log up to 10 logic errors for deeper study
            for i, item in enumerate(items[:10]):
                out.write(
                    f"- **Q{item['question_id']} ({item['db_id']})**: {item['question']}\n"
                )
                out.write(f"  - **Gold SQL**: `{item['gold']}`\n")
                out.write(f"  - **Pred SQL**: `{item['pred']}`\n\n")

    print(f"Analysis complete! Report saved to {to_repo_relative(output_path)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze VeriSQL outputs and categorize errors."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="result_verisql_qwen.jsonl",
        help="Input jsonl file. Relative names are resolved under paper_data/runs/",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="failure_report.md",
        help="Output markdown file. Relative names are written under paper_data/reports/",
    )

    args = parser.parse_args()
    analyze_failures(args.input, args.output)
