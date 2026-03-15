# VeriSQL: Neuro-Symbolic Runtime Verification for Database Analysis Agents

A verifiable agent architecture for Text-to-SQL with formal correctness guarantees.

## 🎯 Key Innovation

VeriSQL combines **Hybrid Verification** with **LLM Agents** through:
1. **Hybrid Verification**: "Static (Z3) + Dynamic (Sandbox)" dual-check.
2. **Dual-Path Generation**: Generate SQL + LTL Specification simultaneously.
3. **AutoFormalizer (ILR)**: Intermediate Logic Representation for disambiguation.
4. **Adversarial Mock Data**: Micro-DB synthesis for boundary testing.
5. **Trace-Guided Repair**: Feedback loop with concrete counter-examples.

## 📁 Project Structure & File Descriptions

```
verisql/
├── agents/
│   ├── graph.py
│   ├── nodes.py
│   └── state.py
├── core/
│   ├── ilr.py
│   ├── dsl.py
│   └── ltl_compiler.py
├── modules/
│   ├── dynamic_verifier.py
│   └── fault_localizer.py
├── utils/
│   ├── __init__.py
│   ├── diagnosis.py
│   ├── spec_utils.py
│   └── z3_utils.py
├── DataBase/
│   └── Bird/              # BIRD benchmark datasets (dev + train)
├── app.py
├── cli.py
├── config.py
├── create_sample_db.py
├── eval_bird.py
├── main.py
├── requirements.txt
└── test_*.py              # Unit/integration test files
```

---

### `agents/` — LangGraph Workflow

#### `agents/graph.py`
Defines the **LangGraph `StateGraph`** that orchestrates the entire VeriSQL pipeline. Builds and wires all nodes in the following order:

```
intent_parser → auto_formalizer → sql_generator → spec_generator
    → symbolic_verifier → dynamic_verifier
        ─── PASS ──→ executor → END
        ─── FAIL ──→ formal_repair → sql_generator (loop, max 3×)
        ─── MAX  ──→ END (with error)
```

Key function: `compile_verisql_app()` — returns the compiled LangGraph application ready for invocation.

#### `agents/nodes.py`
Implements **all LangGraph node functions** that execute within the workflow. Each node reads from `VeriSQLState`, calls one or more LLM prompts or verifier modules, and writes its results back to the state.

| Node | Role |
|---|---|
| `intent_parser_node` | Parses NL query into structured intent JSON (operation type, entity, temporal, filters) |
| `auto_formalizer_node` | Converts parsed intent into ILR (Intermediate Logic Representation) |
| `sql_generator_node` | Generates SQL from ILR using chain-of-thought prompting; respects tie-breaking strategy |
| `spec_generator_node` | Generates a DSL `ConstraintSpec` from ILR for formal verification |
| `symbolic_verifier_node` | Calls Z3-based `SymbolicVerifier` to check SQL against the spec statically |
| `dynamic_verifier_node` | Runs SQL on adversarial micro-databases to detect runtime violations |
| `formal_repair_node` | Calls `FaultLocalizer`, generates structured `PatchAction`s, reformulates feedback |
| `executor_node` | Executes verified SQL on the real SQLite database and returns results |

Also contains `create_llm()` — factory function that creates a `ChatOpenAI` instance configured for the active provider (OpenAI / DeepSeek / Qwen).

#### `agents/state.py`
Defines all **Pydantic data models and the `VeriSQLState` TypedDict** that flows through the graph.

| Model | Description |
|---|---|
| `VeriSQLState` | Main workflow state: carries query, schema, ILR, SQL, spec, verification result, repair history, and final output |
| `VerificationResult` | Verification outcome (`PASS/FAIL/ERROR/SKIP`), counter-example, and per-step details |
| `PatchActionType` | Enum of structured repair action types (`ADD_PREDICATE`, `FIX_BOUNDARY`, `FIX_COLUMN`, etc.) |
| `PatchAction` | Clause-level repair instruction: specifies target clause, current fragment, and suggested replacement |
| `FaultLocalization` | Links a verification failure to a specific SQL clause with associated `PatchAction`s |
| `RepairSuggestion` | Top-level repair record stored in the repair history log |

---

### `core/` — Formal Representation Layer

#### `core/ilr.py`
Defines the **ILR (Intent Logic Representation)** schema — the central intermediate representation that decouples NL understanding from SQL and spec generation, reducing correlated hallucination risk.

Key Pydantic models:
- `ILR` — top-level IR: scope (entity + joins + temporal), operation (SELECT/AGGREGATE/COUNT), constraints, output format
- `FilterConstraint`, `ExistentialConstraint`, `CompositeConstraint` — typed constraint building blocks
- `TieBreakingStrategy` — (`ALL_TIES` / `ARBITRARY_ONE` / `NONE`) controls whether SQL uses subquery or `LIMIT 1`
- `TemporalSpec` — structured temporal range (absolute, relative, or named like Q1–Q4)

#### `core/dsl.py`
Defines the **Constraint DSL** — a simplified, LLM-friendly domain-specific language for expressing query constraints. LLMs generate this DSL instead of raw LTL, then a deterministic compiler converts it to formal logic.

| DSL Type | Description |
|---|---|
| `TemporalConstraint` | Date range, quarter (Q1–Q4), year, or relative time filter |
| `FilterDSL` | Field-level comparison filter (`eq`, `neq`, `gt`, `gte`, `in`, `like`, etc.) |
| `AggregateConstraint` | Aggregate function specification (`sum`, `avg`, `count`, `min`, `max`) |
| `ExistenceConstraint` | EXISTS/NOT EXISTS subquery check |
| `UniquenessConstraint` | Uniqueness constraint over a set of columns |
| `ConstraintSpec` | Top-level spec: scope table + list of `DSLConstraint`s |

#### `core/ltl_compiler.py`
**Deterministic compiler** that transforms `ConstraintSpec` (DSL) into LTL (Linear Temporal Logic) formulas for Z3 verification. Contains no LLM calls — pure symbolic transformation.

Key class: `LTLCompiler.compile(spec)` — produces a `LTLFormula` in the form `∀row ∈ <table>: (φ₁ ∧ φ₂ ∧ …)` by dispatching each DSL constraint to a typed `_compile_*` method.

---

### `modules/` — Verification & Repair Modules

#### `modules/dynamic_verifier.py`
Implements the **dynamic half of the Hybrid Verification pipeline**. Rather than relying solely on symbolic/static analysis, this module synthesizes adversarial data and executes SQL in a sandbox to catch behavioral violations.

Components:
- `MockDBGenerator` — builds a minimal micro-database containing both "golden rows" (satisfy all spec constraints) and "adversarial rows" (violate one constraint at a time). Can also generate rows driven by Z3 counter-examples.
- `SandboxExecutor` — runs SQL on an in-memory SQLite database and collects execution results.
- `DynamicVerifier` — orchestrator: generates mock DB → executes SQL → checks output against the spec → returns `VerificationResult`.

#### `modules/fault_localizer.py`
Implements **C3: Counterexample-Guided Structured Repair** — the key differentiator from vague text-based feedback.

`FaultLocalizer.localize(sql, spec, verification_result)`:
1. Parses the SQL into an AST with `sqlglot`.
2. For each violated spec constraint, searches the AST for a corresponding predicate.
3. Classifies the fault: `MISSING` (predicate absent), `INCORRECT` (wrong value), or `BOUNDARY` (off-by-one).
4. Emits a `PatchAction` pointing to the exact SQL clause and suggesting the fix.

Helper: `format_patch_actions()` — serializes the patch list into a structured prompt string for the SQL repair node.

---

### `utils/` — Utility Modules

#### `utils/z3_utils.py`
Provides the **Z3 SMT-based symbolic verification** layer.

Key classes:
- `SQLConstraintExtractor` — parses a SQL string with `sqlglot` and extracts `WHERE` clause predicates into a normalized constraint dict list.
- `SchemaValidator` — validates that all table/column names in the SQL actually exist in `schema_info`, blocking hallucinated identifiers before Z3 runs.
- `SymbolicVerifier` — encodes both SQL constraints and spec constraints as Z3 formulas, checks satisfiability, and returns a `VerificationResult` with any counter-example.

Top-level function: `verify_sql_against_spec(sql, spec, schema_info)` — convenience wrapper used by nodes and the CLI.

#### `utils/spec_utils.py`
Provides **robust parsing and sanitization** of LLM-generated `ConstraintSpec` JSON.

Key functions:
- `parse_json_from_text(text)` — strips Markdown code fences, removes C-style comments, and extracts valid JSON from raw LLM output.
- `sanitize_constraint(constraint)` — normalises common LLM formatting mistakes (e.g., `"time"` → `"temporal"`, `"where"` → `"filter"`).
- `parse_spec_safely(text, scope_table)` — full pipeline: parse JSON → sanitize each constraint → construct a valid `ConstraintSpec`, falling back to an empty spec on unrecoverable errors.

#### `utils/diagnosis.py`
Provides **smart runtime diagnostics** for SQL execution errors.

Key functions:
- `diagnose_sql_error(error_msg, schema_info)` — heuristically identifies "no such column" and "no such table" errors and suggests the closest valid name using `difflib`.
- `check_result_quality(rows)` — warns when result rows contain a high duplication ratio, indicating a likely missing `DISTINCT` or incorrect `JOIN`.

---

### Root-Level Files

#### `config.py`
Central **configuration module**. Reads environment variables (via `python-dotenv`) to configure:
- **LLM provider**: `openai` / `deepseek` / `qwen`, with per-provider API key and base URL.
- **Model names**: `SQL_MODEL`, `SPEC_MODEL` (defaults per provider).
- **Verification settings**: `MAX_REPAIR_ITERATIONS`, `Z3_TIMEOUT_MS`, `VERIFICATION_MODE`.
- **Schema helpers**: `TEMPORAL_MAPPINGS` (Q1–Q4 date ranges).

Key function: `get_llm_config(provider)` — returns the `{api_key, base_url}` dict for the requested provider.

#### `main.py`
**Programmatic entry point** for running VeriSQL on a single NL query. Initialises `VeriSQLState`, invokes the compiled LangGraph app, and prints a formatted verbose report.

Usage:
```bash
python -m verisql.main "What is the total sales of active products in Q3 2024?" -v
```

#### `app.py`
**Gradio web UI** for interactive use.

- `DatabaseManager` — loads a SQLite file, extracts schema, and optionally loads BIRD-style CSV semantic descriptions.
- Streaming agent pipeline: step-by-step thinking output visible in the UI.
- Displays generated SQL, LTL formula, verification status (static + dynamic), and execution results.

Usage:
```bash
python -m verisql.app
```

#### `cli.py`
**Command-line interface** optimised for batch and iterative testing.

- `CLIDatabaseManager` — CLI-flavored database loader (supports explicit `description_dir`).
- Supports loading questions from `BIRD dev.json` by question ID.
- Outputs structured JSON for easy parsing in automated pipelines.
- Hardcoded default paths point to the BIRD `california_schools` database for quick testing.

Usage:
```bash
python -m verisql.cli --db path/to/db.sqlite --question "..."
```

#### `eval_bird.py`
**BIRD benchmark evaluation script**.

- Loads `dev.json` question set and corresponding gold SQL.
- Calls `run_verisql()` for each question, executes both generated and gold SQL, and compares result sets.
- Tracks per-question metrics (exact match, execution accuracy, verification pass rate).
- Writes a results JSON and prints a summary table.

Usage:
```bash
python verisql/eval_bird.py --dev path/to/dev.json --db-root path/to/dev_databases/
```

#### `create_sample_db.py`
**Test fixture generator**. Creates a minimal e-commerce SQLite database (`sample_store.db`) with four tables (`products`, `customers`, `orders`, `order_items`) populated with sample data, used for local development and smoke tests.

#### `test_*.py` — Test Files

| File | Coverage |
|---|---|
| `test_z3_core.py` | Unit tests for Z3 symbolic verification (`SymbolicVerifier`, `SchemaValidator`) |
| `test_spec_utils.py` | Unit tests for `parse_spec_safely`, `sanitize_constraint`, and `parse_json_from_text` |
| `test_dynamic_verifier.py` | Unit tests for `MockDBGenerator` and `DynamicVerifier` pipeline |
| `test_fault_localizer.py` | Unit tests for `FaultLocalizer` fault localisation and `PatchAction` generation |
| `test_agent_robustness.py` | Integration tests for end-to-end agent robustness under adversarial inputs |
---

## 🚀 Quick Start

```bash
# Reproducible environment from repo root
conda env create -f environment.yml
conda activate verisql

# Or: deps-only
pip install -r verisql/requirements.txt

# Optional test runner
pytest verisql
```

### Environment Variables

Create a `.env` in `verisql/` (or export env vars) with one provider:

```bash
LLM_PROVIDER=openai  # openai | deepseek | qwen

OPENAI_API_KEY=...
# DEEPSEEK_API_KEY=...
# DASHSCOPE_API_KEY=...

# Optional
SQL_MODEL=gpt-4o
SPEC_MODEL=gpt-4o
MAX_REPAIR_ITERATIONS=3
Z3_TIMEOUT_MS=5000
```

### Run (Programmatic / CLI)

```bash
python -m verisql.main "What is the total sales of active products in Q3 2024?" -v
```

### Run (Web UI)

```bash
python -m verisql.app
```

### Run (BIRD Evaluation)

```bash
python -m verisql.eval_bird --pred-source agent --output result_verisql_qwen.jsonl
python -m verisql.analyze_repair_quality --agent result_verisql_qwen.jsonl --no-repair result_norepair_qwen.jsonl --output repair_quality_report.md
python -m verisql.eval_simple --pred-source gold --output simple_regression_gold.jsonl
```

`eval_bird.py` and `eval_simple.py` now emit:

- run metadata in each `*_summary.json`
- token / estimated cost totals when provider usage metadata is available
- a master run index at `paper_data/run_index.jsonl`

If you need paper-grade pricing, set `MODEL_PRICING_JSON` before running evaluations.

## 📦 Dependencies

- `langgraph>=0.1.0` — Agent workflow framework
- `langchain>=0.2.0` — LLM integration
- `z3-solver>=4.12.0` — SMT verification
- `sqlglot>=20.0.0` — SQL parsing / AST
- `openai>=1.0.0` — OpenAI-compatible API client (also used for DeepSeek/Qwen)
- `pydantic>=2.0.0` — Data validation & schemas
- `python-dotenv>=1.0.0` — Environment variable management
- `gradio>=4.0.0` — Demo web UI
- `httpx>=0.25.0` — HTTP client (provider compatibility)
- `pandas>=2.0.0`, `numpy>=1.24.0` — Dynamic sandbox verifier
- `tqdm>=4.0.0` — Benchmark evaluation progress bars

Research prototype.

## 🌟 Recent Updates (Jan 2026)

- **Gradio Web Interface**: Complete UI with streaming Agent thinking process, SQL visualization, and interactive verification feedback.
- **Multi-LLM Support**: Integrated OpenAI, DeepSeek, and Qwen (DashScope) APIs via `create_llm` helper.
- **Enhanced Verification**: Added `SchemaValidator` to prevent hallucinated columns/tables before symbolic verification.
- **Iterative Repair**: Implemented a "feedback loop" where the Agent receives verification errors and auto-corrects SQL (up to 3 times).
- **Semantics-Aware**: Support for loading BIRD-style CSV `database_description` for semantic column understanding.
- **Structured Repair (C3)**: `FaultLocalizer` + `PatchAction` replaces vague text feedback with clause-level repair instructions.

