# Paper Data Workspace

`paper_data/` is the canonical workspace for experiment artifacts used during the
second-stage paper writing process.

## Directory Convention

- `paper_data/runs/`: raw evaluation outputs (`.jsonl`) and auto-generated summaries.
- `paper_data/reports/`: analysis reports derived from run files.
- `paper_data/`: legacy result files that were generated before the workspace was
  standardized. Keep them for reference, but place new outputs under `runs/` and
  `reports/`.

## Naming Rule

- Evaluation runs: `<study_name>.jsonl`
- Run summary: `<study_name>_summary.json`
- Analysis report: `<study_name>_report.md`

Examples:

- `paper_data/runs/result_verisql_qwen.jsonl`
- `paper_data/runs/result_verisql_qwen_summary.json`
- `paper_data/reports/failure_report.md`

## Current Historical Inventory

- Main runs already present:
  - `result_verisql_qwen.jsonl`
  - `result_baseline_qwen.jsonl`
  - `result_nodynamic_qwen.jsonl`
  - `result_norepair_qwen.jsonl`
- Main summaries already present:
  - `result_verisql_qwen_summary.json`
  - `result_baseline_qwen_summary.json`
  - `result_nodynamic_qwen_summary.json`
  - `result_norepair_qwen_summary.json`
- Analysis reports already present:
  - `failure_report.md`

## Recommended Commands

Run files without giving a directory. The scripts now default to `paper_data/`.

```bash
conda activate verisql
python -m verisql.eval_bird --pred-source agent --output result_verisql_qwen.jsonl
python -m verisql.analyze_failures --input result_verisql_qwen.jsonl --output failure_report.md
python -m verisql.find_destructive_repairs --agent result_verisql_qwen.jsonl --no-repair result_norepair_qwen.jsonl --output destructive_repairs_report.md
```
