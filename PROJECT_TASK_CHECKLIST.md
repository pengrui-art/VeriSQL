# VeriSQL Project Task Checklist

Last updated: 2026-03-15

This file is the working project checklist for the ASE 2026 submission phase.
It records:

- what has already been completed,
- what code work still blocks a credible submission,
- where experiment artifacts are stored,
- what to run next.

Older documents such as `VeriSQL_Progress.md` and
`ASE2026_VeriSQL_Task_Plan.md` remain useful as background notes, but this file
is the canonical execution checklist going forward.

## 1. Current Snapshot

- Project stage: research prototype with usable evaluation infrastructure.
- Canonical artifact workspace: `paper_data/`.
- Immediate goal: turn the current prototype into a submission-grade,
  reproducible evaluation package.

## 2. Work Already Completed

### 2.1 Core architecture

- [X] LangGraph workflow with parsing, formalization, SQL generation, verification,
  repair, and execution.
- [X] ILR schema, DSL schema, and deterministic LTL compilation.
- [X] Z3-based symbolic verification.
- [X] Dynamic sandbox verification with adversarial micro-database synthesis.
- [X] Structured repair pipeline based on `FaultLocalizer` and `PatchAction`.
- [X] CLI and Gradio app entry points.

### 2.2 Evaluation infrastructure

- [X] BIRD evaluation runner with SQLite schema loading.
- [X] Async batch execution and JSONL checkpointing.
- [X] Core metrics aggregation: EX / SVR / CAA / latency.
- [X] Gold-mode smoke evaluation path.
- [X] Baseline and ablation run support in `eval_bird.py`.

### 2.3 Analysis assets

- [X] Failure taxonomy script.
- [X] Destructive repair comparison script.
- [X] Historical result files for baseline / full VeriSQL / ablations.
- [X] Preliminary failure report and repair impact report.

### 2.4 Existing tests

- [X] `test_fault_localizer.py`
- [X] `test_z3_core.py`
- [X] `test_dynamic_verifier.py`
- [X] `test_executor_node.py`
- [X] `test_eval_scripts.py`
- [X] `test_extreme_robustness.py`
- [X] `test_agent_robustness.py` as an E2E-style script
- [X] `test_spec_utils.py` as a manual script

## 3. Code Work Still Needed

### 3.1 P0: Must finish before the main paper experiments

- [x] Fix the verification/execution contract.
  - Do not label failed execution as `verified=True`.
  - Do not execute non-read-only SQL in the benchmark path.
  - Decide whether failed verification should stop execution or be logged as
    unverified execution explicitly.
- [x] Remove or refactor duplicated dynamic verification.
  - `verify_sql_against_spec()` is now static-only.
  - runtime falsification stays in `dynamic_verifier_node`.
  - latency and ablation semantics are no longer double-counting dynamic checks.
- [x] Replace all absolute local paths with repo-relative or configurable paths.
  - `cli.py`
  - `test_agent_robustness.py`
  - any remaining local-only defaults
- [ ] Add one clean experiment orchestration entry point.
  - the old root-level helper scripts have been removed
  - keep the canonical workflow under `python -m verisql.*`
  - add a reproducible wrapper only after the pipeline semantics are stable
- [x] Add a reproducible environment spec.
  - `environment.yml` or equivalent
  - make sure `pytest` is included
  - record Python version and critical package versions
- [ ] Add a root `.gitignore` and secret hygiene.
  - `.env` should never be shipped with real keys.

### 3.2 P1: Needed for strong experiments and review defense

- [x] Add run metadata logging for every experiment.
  - provider
  - model names
  - ablation mode
  - dataset slice
  - timestamp
  - git revision if available
- [x] Add token and API cost logging.
- [x] Add stable run naming rules and a master run index under `paper_data/`.
- [x] Quantify repair quality.
  - destructive repairs
  - beneficial repairs
  - patch action frequency
  - per-action success rate
- [x] Add simple-query non-regression evaluation.
  - Spider sample or another easier subset
- [x] Improve packaging and reproducibility docs.
  - one-command evaluation instructions
  - artifact generation instructions
  - paper figure/table source mapping

### 3.3 P2: Paper-support and analysis quality improvements

- [ ] Build figure/table generation scripts from JSONL summaries.
- [ ] Prepare manual annotation sheets for spec quality / failure taxonomy.
- [ ] Add result slicing scripts by database, failure type, and question pattern.
- [ ] Clean README encoding and documentation quality.

## 4. Experiment Artifact Rules

- [X] Canonical artifact root is `paper_data/`.
- [X] New evaluation runs should go to `paper_data/runs/`.
- [X] New analysis reports should go to `paper_data/reports/`.
- [ ] Add a machine-readable run manifest when the next round of experiments starts.

## 5. Next Execution Checklist

### Step A: stabilize the code path

- [x] fix duplicated dynamic verification
- [x] fix verification/execution semantics
- [x] fix path hardcoding
- [x] clean environment spec

### Step B: rerun the canonical experiments

- [ ] full VeriSQL run
- [ ] raw LLM baseline
- [ ] no-dynamic ablation
- [ ] no-repair ablation
- [ ] repair-impact comparison
- [ ] repair-quality report
- [ ] simple-regression run
- [ ] failure taxonomy report

### Step C: prepare paper-ready evidence

- [ ] export final summary tables
- [ ] export failure case studies
- [ ] export threats-to-validity evidence
- [ ] write artifact README for reviewers

## 6. Canonical Commands

```bash
conda activate verisql
python -m verisql.eval_bird --pred-source agent --output result_verisql_qwen.jsonl
python -m verisql.eval_bird --pred-source raw_llm --output result_baseline_qwen.jsonl
python -m verisql.eval_bird --pred-source agent --ablation no_dynamic --output result_nodynamic_qwen.jsonl
python -m verisql.eval_bird --pred-source agent --ablation no_repair --output result_norepair_qwen.jsonl
python -m verisql.analyze_failures --input result_verisql_qwen.jsonl --output failure_report.md
python -m verisql.find_destructive_repairs --agent result_verisql_qwen.jsonl --no-repair result_norepair_qwen.jsonl --output destructive_repairs_report.md
python -m verisql.analyze_repair_quality --agent result_verisql_qwen.jsonl --no-repair result_norepair_qwen.jsonl --output repair_quality_report.md
python -m verisql.eval_simple --pred-source gold --output simple_regression_gold.jsonl
```
