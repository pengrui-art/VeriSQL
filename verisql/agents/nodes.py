"""
LangGraph Workflow Nodes

Implementations of each node in the VeriSQL workflow.
Each node takes state, performs its task, and returns updated state.

Supports multiple LLM providers: OpenAI, DeepSeek, Qwen
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from verisql.agents.state import (
    VeriSQLState,
    VerificationResult,
    RepairSuggestion,
    FaultLocalization,
    PatchAction,
    PatchActionType,
)
from verisql.core.ilr import (
    ILR,
    Scope,
    EntityRef,
    TemporalSpec,
    AggregateOp,
    FilterConstraint,
    OutputSpec,
    ConstraintSource,
)
from verisql.core.dsl import (
    ConstraintSpec,
    TemporalConstraint,
    FilterDSL,
    AggregateConstraint,
)
from verisql.core.ltl_compiler import compile_to_ltl
from verisql.modules.dynamic_verifier import DynamicVerifier
from verisql.modules.fault_localizer import FaultLocalizer, format_patch_actions
from verisql.config import (
    SQL_MODEL,
    SPEC_MODEL,
    MAX_REPAIR_ITERATIONS,
    TEMPORAL_MAPPINGS,
    get_llm_config,
    LLM_PROVIDER,
    LLM_STREAMING,
)
from verisql.utils.sql_safety import validate_read_only_sql
from verisql.utils.llm_usage import merge_usage_summaries, make_usage_event


def create_llm(model: str, temperature: float = 0) -> ChatOpenAI:
    """
    Create an LLM instance with the correct provider configuration.

    Supports OpenAI, DeepSeek, and Qwen with OpenAI-compatible APIs.
    """
    config = get_llm_config()
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=config["api_key"],
        base_url=config["base_url"],
        streaming=LLM_STREAMING,
    )


# ============== Prompts ==============

INTENT_PARSER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an intent parser for database queries. 
Extract the structured intent from the natural language query.

IMPORTANT: Your output must be PURE JSON. Do NOT include any comments (like // or /* */) inside the JSON.

Schema info contains table structures and semantic descriptions. 
CRITICAL RULES: 
1. **SELECT vs AGGREGATE**: 
   - If user asks "Which [Entity]..." or "What is the [Entity]...", operation is "SELECT" targeting that Entity logic (e.g., Name).
   - ONLY use "COUNT"/"AGGREGATE" if user asks "How many..." or "Calculate the total...".
   - Example: "Which county has most schools?" -> op="SELECT", target="County" (Ordered by count).
   - Example: "How many schools in X?" -> op="COUNT", target="schools".
2. Match semantic terms to real columns using Schema descriptions.
3. Distinguish between EXPLICIT filters (from user) and IMPLICIT business rules.

Output JSON with:
- operation: "AGGREGATE" | "SELECT" | "COUNT"
- aggregate_function: "SUM" | "AVG" | "COUNT" | "MIN" | "MAX" (if aggregate)
- target_column: the column to retrieve (e.g., "County").
- entity: primary table name
- secondary_entities: list of other tables needed for joins
- temporal: any time references (Q1-Q4, year, date range)
- filters: explicit filter conditions mentioned
- implicit_filters: likely implicit business rules

Schema info: {schema_info}""",
        ),
        ("human", "{query}"),
    ]
)

AUTO_FORMALIZER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an AutoFormalizer. Convert parsed intent to ILR (Intent Logic Representation) JSON.

IMPORTANT: Output PURE JSON only. No comments, no markdown, no extra text.

You MUST output a JSON object with EXACTLY these top-level keys: raw_query, scope, operation, constraints, output.

REQUIRED JSON SCHEMA (follow this exactly):
{{
  "raw_query": "<copy the original natural language query here>",
  "scope": {{
    "entity": {{
      "table": "<primary table name>",
      "alias": null
    }},
    "temporal": null,
    "joins": []
  }},
  "operation": {{
    "type": "SELECT",
    "columns": ["col1", "col2"],
    "distinct": false
  }},
  "constraints": [],
  "output": {{
    "format": "TABLE",
    "tie_strategy": "ALL_TIES",
    "limit": null
  }}
}}

OPERATION TYPES — use exactly one:
- SELECT: {{"type": "SELECT", "columns": ["col1", "col2"], "distinct": false}}
- AGGREGATE: {{"type": "AGGREGATE", "function": "SUM|AVG|COUNT|MIN|MAX", "target": "col_name", "distinct": false}}
- COUNT: {{"type": "COUNT", "target": null, "distinct": false}}

SCOPE JOINS (only if multi-table query):
"joins": [{{"target_entity": {{"table": "other_table", "alias": null}}, "join_type": "INNER", "on_condition": "t1.id = t2.fk"}}]

SCOPE TEMPORAL (only if time filter exists):
"temporal": {{"type": "NAMED", "value": "Q3", "resolved_start": "2024-07-01", "resolved_end": "2024-09-30", "column": "date_col"}}
temporal.type valid values: "ABSOLUTE" (specific date range), "RELATIVE" (e.g. last 30 days), "NAMED" (Q1-Q4, year name)

CONSTRAINTS (optional, only for explicit filters in the query):
{{"type": "FilterConstraint", "field": "status", "op": "!=", "value": "cancelled", "source": "EXPLICIT"}}
FilterConstraint.op valid values: "==" "!=" ">" "<" ">=" "<=" "IN" "NOT_IN" "LIKE" "IS_NULL" "IS_NOT_NULL"
IMPORTANT: Use "==" (double equals) NOT "=" for equality.

RULES:
1. raw_query MUST equal the original query string — never leave it empty.
2. scope.entity.table = the primary table from parsed intent.
3. For "highest/lowest X" → tie_strategy: "ALL_TIES"; for "top 1" → "ARBITRARY_ONE"; otherwise "NONE".
4. Temporal: Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec.
5. Do NOT add implicit constraints unless explicitly stated in the query.""",
        ),
        (
            "human",
            """Parsed intent: {parsed_intent}
Original query: {query}

Generate ILR JSON (pure JSON only, no markdown):""",
        ),
    ]
)

SQL_GENERATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert SQL generator. Generate SQL based on the ILR (Intent Logic Representation).

**OUTPUT FORMAT**:
Thinking:
1. ... (step-by-step reasoning)
2. Strategy for Extremes: (Must explicitly state 'Subquery' or 'Limit 1')
...
```sql
SELECT ...
```

**CRITICAL RULES**:
1. **NO HALLUCINATIONS**: ONLY use table and column names explicitly listed in the Schema.
2. **EXTREMES & TIES (Crucial)**:
   - **CHECK ILR**: Look at `output.tie_strategy`.
   - **ALL_TIES** (Default): You **MUST** use a **SUBQUERY** (e.g., `WHERE x = (SELECT MAX(x)...)`) to return all tied rows.
   - **ARBITRARY_ONE**: Use `ORDER BY ... LIMIT 1`.
   - **Why?** We must respect the formal intent. "Which school..." usually means "which schools..." if ties exist.
   - **Example**: "Find the student with the highest score"
     - *Strategy=ALL_TIES*: `SELECT name FROM students WHERE score = (SELECT MAX(score) FROM students)`
     - *Strategy=ARBITRARY_ONE*: `SELECT name FROM students ORDER BY score DESC LIMIT 1`

3. **CALCULATION SAFETY**:
   - **CASTING (CRITICAL)**: SQLite performs INTEGER DIVISION. `1/2 = 0`.
     - You **MUST** use `CAST(col AS REAL)` for division.
     - Example: `CAST(NumGE1500 AS REAL) / NumTstTakr`
   - **ZERO CHECK**: `WHERE Denominator != 0` (e.g., `NumTstTakr != 0`)
   - **LARGE RESULTS**: If exploring data (e.g. "list all cities"), consider `COUNT(*)` first or use `LIMIT 50` if you suspect >100 rows.

4. **COUNT AGGREGATION**:
   - Prefer `COUNT(*)` for general "how many" questions (e.g., "count orders").
   - When using **JOINs**, be careful with row multiplication. Use `COUNT(DISTINCT table.id)` if necessary.
   - Example: "How many cities have schools?" -> `SELECT COUNT(DISTINCT city_id) ...` (if joining schools).

5. **RUNTIME FEEDBACK HANDLER**:
   - If `{execution_feedback}` says "Returned 0 rows":
     - **DIAGNOSE**: Did you use a strict string filter (e.g., `City = 'Los Angeles'`)?
     - **FIX**: Try relaxing it: use `LIKE '%Los Angeles%'` or check if the column uses abbreviations (e.g., 'CA' instead of 'California').
     - **ACTION**: You **MUST** change the SQL. Do not return the same SQL.

6. **DIALECT**: SQLite.

Schema: {schema_info}""",
        ),
        (
            "human",
            """ILR: {ilr}

{repair_feedback}
{execution_feedback}

Generate Thought Process and SQL:""",
        ),
    ]
)

SPEC_GENERATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a constraint specification generator. Generate a ConstraintSpec in DSL format.

**OUTPUT FORMAT**: Pure JSON only. No comments, no markdown, no explanations.

**REQUIRED JSON STRUCTURE**:
{{
  "scope_table": "table_name",
  "scope_description": "brief summary",
  "constraints": [...]
}}

**CONSTRAINT TYPES** (use the exact format below):

1. **temporal** - Date/time constraints:
   {{
     "type": "temporal",
     "constraint_type": "quarter",
     "quarter": "Q3",
     "year": 2024,
     "column": "order_date"
   }}
   constraint_type can be: "quarter", "date_range", "year", "relative"
   quarter can be: "Q1", "Q2", "Q3", "Q4"

2. **filter** - Value filters:
   {{
     "type": "filter",
     "field": "status",
     "operator": "neq",
     "value": "cancelled",
     "is_implicit": false
   }}
   operator can be: "eq", "neq", "gt", "lt", "gte", "lte", "in", "not_in", "like"

3. **aggregate** - Aggregation constraint:
   {{
     "type": "aggregate",
     "function": "max",
     "column": "amount",
     "alias": "highest_amount"
   }}
   function can be: "sum", "avg", "count", "min", "max"

4. **existence** - EXISTS subquery:
   {{
     "type": "existence",
     "exists": true,
     "related_table": "customers",
     "join_condition": "orders.customer_id = customers.id"
   }}

5. **uniqueness** - DISTINCT constraint:
   {{
     "type": "uniqueness",
     "columns": ["customer_id", "order_date"]
   }}

**IMPORTANT RULES**:
1. Only add constraints EXPLICITLY mentioned in the query
2. Use REAL column names from the Schema
3. If query is simple (like "highest X"), use an aggregate constraint with "max"
4. For "lowest", use "min"; for "count", use "count"
5. If no specific constraints needed, return empty constraints list

Schema: {schema_info}""",
        ),
        (
            "human",
            """ILR: {ilr}
Original query: {query}

Generate ConstraintSpec JSON:""",
        ),
    ]
)


import json
import re


def parse_json_from_markdown(text: str) -> Dict[str, Any]:
    """
    Robustly extract JSON from text that may contain Markdown code blocks
    or other conversational noise.
    """
    try:
        # 1. Try to find JSON inside markdown code blocks
        pattern = r"```(?:json)?\s*(.*?)```"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            json_str = match.group(1).strip()
        else:
            # 2. Heuristic: Find first '{' and last '}'
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                json_str = text[start : end + 1]
            else:
                json_str = text.strip()

        # 3. Remove C-style comments (// ...) which are invalid in std JSON but common in LLM output
        # (Simple regex, might be fragile for URLs but sufficient for this domain)
        json_str = re.sub(r"//.*", "", json_str)

        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {str(e)} | Content: {text[:100]}...")


# ============== ILR Normalization Helpers ==============

_TEMPORAL_TYPE_MAP = {
    "RANGE": "ABSOLUTE",
    "DATE_RANGE": "ABSOLUTE",
    "EXACT": "ABSOLUTE",
    "YEAR": "NAMED",
    "MONTH": "NAMED",
    "QUARTER": "NAMED",
}

_OP_MAP = {
    "=": "==",
    "<>": "!=",
    "NOT LIKE": "!=",  # approximate
}


def _normalize_ilr_dict(d: dict) -> dict:
    """Normalize common LLM enum value mistakes before Pydantic validation."""
    # Normalize temporal.type
    scope = d.get("scope")
    if isinstance(scope, dict):
        temporal = scope.get("temporal")
        if isinstance(temporal, dict):
            t = temporal.get("type", "")
            temporal["type"] = _TEMPORAL_TYPE_MAP.get(t, t)

    # Normalize constraint operator values
    for c in d.get("constraints", []):
        if isinstance(c, dict) and "op" in c:
            c["op"] = _OP_MAP.get(c["op"], c["op"])

    return d


# ============== Node Implementations ==============


def intent_parser_node(state: VeriSQLState) -> Dict[str, Any]:
    """
    Module 1: Parse natural language query to extract intent.
    """
    try:
        llm = create_llm(SQL_MODEL)
        # REMOVED JsonOutputParser to handle chatty models better
        chain = INTENT_PARSER_PROMPT | llm

        response = chain.invoke(
            {"query": state["query"], "schema_info": state.get("schema_info", {})}
        )
        llm_usage = merge_usage_summaries(
            state.get("llm_usage"),
            make_usage_event(
                response,
                stage="intent_parser",
                model=SQL_MODEL,
                provider=LLM_PROVIDER,
            ),
        )

        parsed_intent = parse_json_from_markdown(response.content)

        # Store parsed intent for next stage
        # (We pass it through to auto_formalizer)
        return {
            "parsed_intent": parsed_intent,
            "llm_usage": llm_usage,
            "errors": state.get("errors", []),
        }
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [f"Intent parsing failed: {str(e)}"]
        }


def auto_formalizer_node(state: VeriSQLState) -> Dict[str, Any]:
    """
    Module 2: Convert parsed intent to ILR (Intent Logic Representation).

    This is the KEY INNOVATION - creating a common reference point
    that reduces correlated hallucination.
    """
    try:
        llm = create_llm(SPEC_MODEL)  # Can use different model!
        chain = AUTO_FORMALIZER_PROMPT | llm

        response = chain.invoke(
            {"parsed_intent": state.get("parsed_intent", {}), "query": state["query"]}
        )
        llm_usage = merge_usage_summaries(
            state.get("llm_usage"),
            make_usage_event(
                response,
                stage="auto_formalizer",
                model=SPEC_MODEL,
                provider=LLM_PROVIDER,
            ),
        )

        ilr_dict = parse_json_from_markdown(response.content)

        # Normalize common enum value mismatches before Pydantic validation
        ilr_dict = _normalize_ilr_dict(ilr_dict)

        # Validate and create ILR object; log raw output on failure for debugging
        try:
            ilr = ILR(**ilr_dict)
        except Exception as validation_err:
            logger.warning(
                f"ILR Pydantic validation failed: {validation_err}. "
                f"Raw LLM output: {response.content[:300]}"
            )
            raise validation_err

        return {"ilr": ilr, "llm_usage": llm_usage, "errors": state.get("errors", [])}
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [f"AutoFormalizer failed: {str(e)}"]
        }


def sql_generator_node(state: VeriSQLState) -> Dict[str, Any]:
    """
    Module 3A: Generate SQL from ILR.
    """
    try:
        llm = create_llm(SQL_MODEL)

        # Include repair feedback if in repair loop
        repair_feedback = ""
        if state.get("current_feedback"):
            repair_feedback = f"REPAIR FEEDBACK: {state['current_feedback']}"

        chain = SQL_GENERATOR_PROMPT | llm

        # execution_feedback: runtime result of the previous SQL (empty on first attempt)
        execution_feedback = state.get("execution_feedback", "")

        result = chain.invoke(
            {
                "ilr": state["ilr"].model_dump_json() if state.get("ilr") else "{}",
                "schema_info": state.get("schema_info", {}),
                "dialect": "sqlite",
                "repair_feedback": repair_feedback,
                "execution_feedback": execution_feedback,
            }
        )
        llm_usage = merge_usage_summaries(
            state.get("llm_usage"),
            make_usage_event(
                result,
                stage="sql_generator",
                model=SQL_MODEL,
                provider=LLM_PROVIDER,
                extra={"repair_iteration": state.get("repair_count", 0)},
            ),
        )

        # Extract SQL from response using Regex for robustness
        import re

        content = result.content

        # Pattern 1: Markdown code block ```sql ... ```
        pattern_block = r"```(?:sql)?\s*(.*?)```"
        match = re.search(pattern_block, content, re.DOTALL | re.IGNORECASE)
        if match:
            sql = match.group(1).strip()
        else:
            # Pattern 2: Raw text, maybe just the SQL?
            # We assume the model followed instruction, but it might have chat text.
            # Heuristic: Look for SELECT ...
            pattern_select = r"(SELECT\s+.*)"
            match_select = re.search(pattern_select, content, re.DOTALL | re.IGNORECASE)
            if match_select:
                sql = match_select.group(1).strip()
            else:
                # Fallback: take the whole thing
                sql = content.strip()

        # Clean up common debris
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip()

        return {"sql": sql, "llm_usage": llm_usage, "errors": state.get("errors", [])}
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [f"SQL generation failed: {str(e)}"]
        }


def spec_generator_node(state: VeriSQLState) -> Dict[str, Any]:
    """
    Module 3B: Generate Constraint Specification from ILR.

    Uses a DIFFERENT model than SQL generator to reduce correlation!
    """
    try:
        llm = create_llm(SPEC_MODEL)
        chain = SPEC_GENERATOR_PROMPT | llm

        response = chain.invoke(
            {
                "ilr": state["ilr"].model_dump_json() if state.get("ilr") else "{}",
                "query": state["query"],
                "schema_info": state.get("schema_info", {}),
            }
        )
        llm_usage = merge_usage_summaries(
            state.get("llm_usage"),
            make_usage_event(
                response,
                stage="spec_generator",
                model=SPEC_MODEL,
                provider=LLM_PROVIDER,
                extra={"repair_iteration": state.get("repair_count", 0)},
            ),
        )

        spec_dict = parse_json_from_markdown(response.content)

        constraint_spec = ConstraintSpec(**spec_dict)

        # Compile to LTL
        ltl_formula = compile_to_ltl(constraint_spec)

        return {
            "constraint_spec": constraint_spec,
            "ltl_formula": str(ltl_formula),
            "llm_usage": llm_usage,
            "errors": state.get("errors", []),
        }
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [f"Spec generation failed: {str(e)}"]
        }


def symbolic_verifier_node(state: VeriSQLState) -> Dict[str, Any]:
    """
    Module 4: Verify SQL against Spec using symbolic verification.

    This is the CORE of VeriSQL - pre-verification before execution.
    """
    from verisql.utils.z3_utils import verify_sql_against_spec

    try:
        sql = state.get("sql", "")
        constraint_spec = state.get("constraint_spec")

        if not sql or not constraint_spec:
            return {
                "verification_result": VerificationResult(
                    status="ERROR", message="Missing SQL or constraint spec"
                ),
                "errors": state.get("errors", []),
            }

        # Perform verification
        schema_info = state.get("schema_info")
        result = verify_sql_against_spec(sql, constraint_spec, schema_info)

        return {"verification_result": result, "errors": state.get("errors", [])}
    except Exception as e:
        return {
            "verification_result": VerificationResult(
                status="ERROR", message=f"Verification error: {str(e)}"
            ),
            "errors": state.get("errors", []) + [f"Verification failed: {str(e)}"],
        }


def dynamic_verifier_node(state: VeriSQLState) -> Dict[str, Any]:
    """
    Module 4B: Dynamic Verification (Sandbox).

    Runs AFTER symbolic verifier. If symbolic passed, we try to falsify with dynamic tests.
    """
    try:
        # Check if ablation disables dynamic verification
        if state.get("ablation_mode") == "no_dynamic":
            return {}  # Skip dynamic verification completely

        # 1. Check if Static Check already failed
        prev_result = state.get("verification_result")

        # If static failed or error, we skip dynamic to save time/compute
        if not prev_result or prev_result.status != "PASS":
            return {}  # No change to state

        # 2. Prepare inputs
        sql = state.get("sql", "")
        constraint_spec = state.get("constraint_spec")
        schema_info = state.get("schema_info", {})

        if not sql or not constraint_spec:
            return {}

        # 3. Run Dynamic Verifier
        verifier = DynamicVerifier(schema_info)
        result = verifier.verify(sql, constraint_spec)

        # 4. Integrate results
        # We preserve the original result object but update it if dynamic fails or adds info
        updated_result = prev_result.model_copy()

        # Preserve static verification details and append the runtime check.
        updated_result.verification_details["Dynamic Sandbox"] = result.status

        if result.status != "PASS":
            # Dynamic check failed! Overwrite global status
            updated_result.status = result.status
            updated_result.message = f"[Dynamic] {result.message}"
            updated_result.counterexample = result.counterexample
            updated_result.missing_constraints = result.missing_constraints

        return {
            "verification_result": updated_result,
            "errors": state.get("errors", []),
        }

    except Exception as e:
        # If dynamic verifier crashes, we log it but maybe don't block the whole pipeline if static passed?
        # For now, let's treat it as an error to be safe.
        return {
            "errors": state.get("errors", [])
            + [f"Dynamic Verification failed: {str(e)}"]
        }


def formal_repair_node(state: VeriSQLState) -> Dict[str, Any]:
    """
    Module 5: Counterexample-Guided Structured Repair.

    Core C3 Innovation: Instead of vague text feedback, we:
    1. Use FaultLocalizer to map counterexamples to SQL clause-level faults
    2. Generate structured PatchActions (ADD_PREDICATE, FIX_BOUNDARY, etc.)
    3. Format them as deterministic repair instructions for the SQL generator
    """
    try:
        verification_result = state.get("verification_result")
        if not verification_result or verification_result.status == "PASS":
            return state

        sql = state.get("sql", "")
        constraint_spec = state.get("constraint_spec")

        # ---- Step 1: Fault Localization ----
        fault_localizer = FaultLocalizer()
        faults = []

        if constraint_spec and sql:
            faults = fault_localizer.localize(sql, constraint_spec, verification_result)

        # ---- Step 2: Flatten PatchActions ----
        all_patch_actions = []
        for fault in faults:
            all_patch_actions.extend(fault.patch_actions)

        # ---- Step 3: Format structured feedback ----
        # Use the new structured format instead of free text
        structured_feedback = format_patch_actions(faults)

        # Fallback to legacy text if no structured faults were found
        if not structured_feedback:
            feedback_parts = []
            if verification_result.missing_constraints:
                feedback_parts.append(
                    f"Missing constraints: {', '.join(verification_result.missing_constraints)}"
                )
            if verification_result.counterexample:
                feedback_parts.append(
                    f"Counterexample: {verification_result.counterexample}"
                )
            structured_feedback = (
                "\n".join(feedback_parts) or verification_result.message
            )

        # ---- Step 4: Create structured repair record ----
        repair = RepairSuggestion(
            issue_type=(
                verification_result.message.split(":")[0]
                if ":" in verification_result.message
                else "constraint_violation"
            ),
            description=verification_result.message,
            suggested_fix=structured_feedback,
            confidence=max((a.confidence for a in all_patch_actions), default=0.5),
            fault_localizations=faults,
        )

        repair_history = state.get("repair_history", [])
        repair_history.append(repair)

        return {
            "current_feedback": structured_feedback,
            "fault_localizations": faults,
            "patch_actions": all_patch_actions,
            "repair_history": repair_history,
            "repair_count": state.get("repair_count", 0) + 1,
            "errors": state.get("errors", []),
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        return {
            "errors": state.get("errors", []) + [f"Repair generation failed: {str(e)}"]
        }


def executor_node(state: VeriSQLState) -> Dict[str, Any]:
    """
    Module 6: Execute verified SQL against real database.

    Supports:
    - SQLite file-based DB (from state['db_path'])
    - Graceful fallback when no DB is available (marks as verified-only)
    """
    import sqlite3
    import time

    try:
        sql = state.get("sql", "")
        db_path = state.get("db_path")
        verification_result = state.get("verification_result")
        is_verified = bool(
            verification_result and verification_result.status == "PASS"
        )

        if not sql:
            return {
                "execution_status": "failed",
                "errors": state.get("errors", []) + ["No SQL to execute"],
            }

        if verification_result and verification_result.status != "PASS":
            message = (
                "Execution blocked because the SQL did not pass verification "
                f"({verification_result.status})."
            )
            return {
                "final_sql": sql,
                "execution_status": "failed",
                "final_result": {
                    "sql": sql,
                    "verified": False,
                    "error": message,
                },
                "errors": state.get("errors", []) + [message],
            }

        is_safe, safety_error = validate_read_only_sql(sql)
        if not is_safe:
            return {
                "final_sql": sql,
                "execution_status": "failed",
                "final_result": {
                    "sql": sql,
                    "verified": False,
                    "error": safety_error,
                },
                "errors": state.get("errors", []) + [safety_error],
            }

        if not db_path:
            if is_verified:
                return {
                    "final_sql": sql,
                    "execution_status": "verified",
                    "final_result": {
                        "sql": sql,
                        "verified": True,
                        "repair_iterations": state.get("repair_count", 0),
                        "note": "No db_path provided - SQL verified but not executed",
                    },
                    "errors": state.get("errors", []),
                }

            message = "No db_path provided and SQL is not verified for execution"
            return {
                "final_sql": sql,
                "execution_status": "failed",
                "final_result": {
                    "sql": sql,
                    "verified": False,
                    "error": message,
                },
                "errors": state.get("errors", []) + [message],
            }

        # If we have a real database, execute against it
        if db_path:
            start_time = time.time()
            try:
                conn = sqlite3.connect(db_path)

                # Robustness: Prevent infinite loops or extremely long executions (Timeout ~ 10s)
                def progress_handler():
                    if time.time() - start_time > 10.0:
                        return (
                            1  # non-zero return value interrupts the sqlite execution
                        )
                    return 0

                conn.set_progress_handler(progress_handler, 10000)

                cursor = conn.cursor()
                cursor.execute(sql)

                columns = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )

                # Robustness: Prevent memory overflow by fetching at most 1001 rows
                rows = cursor.fetchmany(1001)

                elapsed_ms = (time.time() - start_time) * 1000
                conn.close()

                return {
                    "final_sql": sql,
                    "execution_status": "executed",
                    "final_result": {
                        "sql": sql,
                        "verified": is_verified,
                        "repair_iterations": state.get("repair_count", 0),
                        "columns": columns,
                        "row_count": len(rows),
                        "rows": rows[:100],  # Cap at 100 rows for state size
                        "execution_time_ms": round(elapsed_ms, 2),
                    },
                    "errors": state.get("errors", []),
                }
            except sqlite3.Error as db_err:
                # Make sure connection is closed even on fail
                try:
                    conn.close()
                except:
                    pass

                return {
                    "final_sql": sql,
                    "execution_status": "failed",
                    "final_result": {
                        "sql": sql,
                        "verified": is_verified,
                        "error": str(db_err),
                    },
                    "errors": state.get("errors", [])
                    + [f"DB execution error: {str(db_err)}"],
                }

        # No database path — mark as verified-only (acceptable for Text-to-SQL benchmarks)
        return {
            "final_sql": sql,
            "execution_status": "verified",
            "final_result": {
                "sql": sql,
                "verified": True,
                "repair_iterations": state.get("repair_count", 0),
                "note": "No db_path provided — SQL verified but not executed",
            },
            "errors": state.get("errors", []),
        }
    except Exception as e:
        return {
            "execution_status": "failed",
            "errors": state.get("errors", []) + [f"Execution failed: {str(e)}"],
        }
