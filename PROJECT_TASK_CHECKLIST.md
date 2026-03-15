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

- [x] LangGraph workflow with parsing, formalization, SQL generation, verification,
      repair, and execution.
- [x] ILR schema, DSL schema, and deterministic LTL compilation.
- [x] Z3-based symbolic verification.
- [x] Dynamic sandbox verification with adversarial micro-database synthesis.
- [x] Structured repair pipeline based on `FaultLocalizer` and `PatchAction`.
- [x] CLI and Gradio app entry points.

### 2.2 Evaluation infrastructure

- [x] BIRD evaluation runner with SQLite schema loading.
- [x] Async batch execution and JSONL checkpointing.
- [x] Core metrics aggregation: EX / SVR / CAA / latency.
- [x] Gold-mode smoke evaluation path.
- [x] Baseline and ablation run support in `eval_bird.py`.

### 2.3 Analysis assets

- [x] Failure taxonomy script.
- [x] Destructive repair comparison script.
- [x] Historical result files for baseline / full VeriSQL / ablations.
- [x] Preliminary failure report and repair impact report.

### 2.4 Existing tests

- [x] `test_fault_localizer.py`
- [x] `test_z3_core.py`
- [x] `test_dynamic_verifier.py`
- [x] `test_executor_node.py`
- [x] `test_eval_scripts.py`
- [x] `test_extreme_robustness.py`
- [x] `test_agent_robustness.py` as an E2E-style script
- [x] `test_spec_utils.py` as a manual script

## 3. Code Work Still Needed

### 3.1 P0: Must finish before the main paper experiments

- [ ] Fix the verification/execution contract.
  - Do not label failed execution as `verified=True`.
  - Do not execute non-read-only SQL in the benchmark path.
  - Decide whether failed verification should stop execution or be logged as
    unverified execution explicitly.
- [ ] Remove or refactor duplicated dynamic verification.
  - `verify_sql_against_spec()` already includes dynamic verification.
  - The graph currently also runs `dynamic_verifier_node`.
  - This must be clarified before reporting latency or ablation numbers.
- [ ] Replace all absolute local paths with repo-relative or configurable paths.
  - `cli.py`
  - `test_agent_robustness.py`
  - any remaining local-only defaults
- [ ] Repair broken helper scripts.
  - `run_baseline.py` currently references a missing `test_api.py`.
  - baseline orchestration should be renamed or fixed.
- [ ] Add a reproducible environment spec.
  - `environment.yml` or equivalent
  - make sure `pytest` is included
  - record Python version and critical package versions
- [ ] Add a root `.gitignore` and secret hygiene.
  - `.env` should never be shipped with real keys.

### 3.2 P1: Needed for strong experiments and review defense

- [ ] Add run metadata logging for every experiment.
  - provider
  - model names
  - ablation mode
  - dataset slice
  - timestamp
  - git revision if available
- [ ] Add token and API cost logging.
- [ ] Add stable run naming rules and a master run index under `paper_data/`.
- [ ] Quantify repair quality.
  - destructive repairs
  - beneficial repairs
  - patch action frequency
  - per-action success rate
- [ ] Add simple-query non-regression evaluation.
  - Spider sample or another easier subset
- [ ] Improve packaging and reproducibility docs.
  - one-command evaluation instructions
  - artifact generation instructions
  - paper figure/table source mapping

### 3.3 P2: Paper-support and analysis quality improvements

- [ ] Build figure/table generation scripts from JSONL summaries.
- [ ] Prepare manual annotation sheets for spec quality / failure taxonomy.
- [ ] Add result slicing scripts by database, failure type, and question pattern.
- [ ] Clean README encoding and documentation quality.

## 4. Experiment Artifact Rules

- [x] Canonical artifact root is `paper_data/`.
- [x] New evaluation runs should go to `paper_data/runs/`.
- [x] New analysis reports should go to `paper_data/reports/`.
- [ ] Add a machine-readable run manifest when the next round of experiments starts.

## 5. Next Execution Checklist

### Step A: stabilize the code path

- [ ] fix duplicated dynamic verification
- [ ] fix verification/execution semantics
- [ ] fix path hardcoding
- [ ] clean environment spec

### Step B: rerun the canonical experiments

- [ ] full VeriSQL run
- [ ] raw LLM baseline
- [ ] no-dynamic ablation
- [ ] no-repair ablation
- [ ] repair-impact comparison
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
```
