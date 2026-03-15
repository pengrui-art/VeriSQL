"""
Spec Utilities

Provides robust parsing and sanitization of LLM-generated ConstraintSpec JSON.
Handles common LLM output errors and provides safe fallback behavior.
"""
import json
import re
import logging
from typing import Dict, Any, Optional, List, Union

from verisql.core.dsl import (
    ConstraintSpec,
    DSLConstraint,
    TemporalConstraint,
    FilterDSL,
    AggregateConstraint,
    ExistenceConstraint,
    UniquenessConstraint,
)

logger = logging.getLogger(__name__)


# Valid values for various constraint fields
VALID_CONSTRAINT_TYPES = {"temporal", "filter", "aggregate", "existence", "uniqueness"}
VALID_FILTER_OPERATORS = {"eq", "neq", "gt", "lt", "gte", "lte", "in", "not_in", "like", "is_null", "is_not_null"}
VALID_TEMPORAL_TYPES = {"date_range", "quarter", "year", "relative"}
VALID_AGGREGATE_FUNCTIONS = {"sum", "avg", "count", "min", "max"}
VALID_QUARTERS = {"Q1", "Q2", "Q3", "Q4"}


def parse_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract JSON from text that may contain Markdown code blocks or noise.
    """
    try:
        # 1. Try to find JSON inside markdown code blocks
        pattern = r"```(?:json)?\s*(.*?)```"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            json_str = match.group(1).strip()
        else:
            # 2. Find first '{' and last '}'
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                json_str = text[start : end + 1]
            else:
                json_str = text.strip()
        
        # 3. Remove C-style comments
        json_str = re.sub(r"//.*", "", json_str)
        
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {str(e)}")


def sanitize_constraint(constraint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Sanitize a single constraint dict. Returns None if the constraint is invalid.
    """
    if not isinstance(constraint, dict):
        return None
    
    # Get and normalize the type
    ctype = constraint.get("type", "").lower().strip()
    
    # Handle common LLM mistakes
    if ctype in ("temporal", "time", "date", "datetime"):
        ctype = "temporal"
    elif ctype in ("filter", "where", "condition"):
        ctype = "filter"
    elif ctype in ("aggregate", "aggregation", "agg"):
        ctype = "aggregate"
    elif ctype in ("existence", "exists", "exist"):
        ctype = "existence"
    elif ctype in ("uniqueness", "unique", "distinct"):
        ctype = "uniqueness"
    
    if ctype not in VALID_CONSTRAINT_TYPES:
        logger.warning(f"Unknown constraint type '{ctype}', skipping")
        return None
    
    constraint["type"] = ctype
    
    # Fix type-specific issues
    if ctype == "temporal":
        return _sanitize_temporal(constraint)
    elif ctype == "filter":
        return _sanitize_filter(constraint)
    elif ctype == "aggregate":
        return _sanitize_aggregate(constraint)
    elif ctype == "existence":
        return _sanitize_existence(constraint)
    elif ctype == "uniqueness":
        return _sanitize_uniqueness(constraint)
    
    return constraint


def _sanitize_temporal(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sanitize temporal constraint."""
    # Ensure constraint_type exists
    ctype = c.get("constraint_type", "").lower().strip()
    
    # Normalize common variations
    if ctype in ("quarter", "q"):
        ctype = "quarter"
    elif ctype in ("date_range", "daterange", "range"):
        ctype = "date_range"
    elif ctype in ("year", "y"):
        ctype = "year"
    elif ctype in ("relative", "rel"):
        ctype = "relative"
    
    if ctype not in VALID_TEMPORAL_TYPES:
        # Try to infer from other fields
        if c.get("quarter"):
            ctype = "quarter"
        elif c.get("start_date") or c.get("end_date"):
            ctype = "date_range"
        elif c.get("year") and not c.get("quarter"):
            ctype = "year"
        elif c.get("relative_expr"):
            ctype = "relative"
        else:
            ctype = "date_range"  # Default fallback
    
    c["constraint_type"] = ctype
    
    # Ensure column exists
    if not c.get("column"):
        c["column"] = "date"
    
    # Normalize quarter field
    if c.get("quarter"):
        quarter = str(c["quarter"]).upper().strip()
        if not quarter.startswith("Q"):
            quarter = f"Q{quarter}"
        if quarter in VALID_QUARTERS:
            c["quarter"] = quarter
    
    # Convert year to int if needed
    if c.get("year"):
        try:
            c["year"] = int(c["year"])
        except (ValueError, TypeError):
            c.pop("year", None)
    
    return c


def _sanitize_filter(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sanitize filter constraint."""
    # Ensure field exists
    if not c.get("field"):
        # Try common alternatives
        c["field"] = c.get("column") or c.get("col") or c.get("name") or ""
        if not c["field"]:
            logger.warning("Filter constraint missing 'field', skipping")
            return None
    
    # Normalize operator
    op = c.get("operator", "").lower().strip()
    
    # Handle common variations
    op_mapping = {
        "=": "eq", "==": "eq", "equals": "eq", "equal": "eq",
        "!=": "neq", "<>": "neq", "not_equal": "neq", "not_equals": "neq",
        ">": "gt", "greater": "gt", "greater_than": "gt",
        "<": "lt", "less": "lt", "less_than": "lt",
        ">=": "gte", "greater_or_equal": "gte",
        "<=": "lte", "less_or_equal": "lte",
        "contains": "like", "ilike": "like",
        "null": "is_null", "isnull": "is_null",
        "notnull": "is_not_null", "not_null": "is_not_null",
    }
    
    op = op_mapping.get(op, op)
    
    if op not in VALID_FILTER_OPERATORS:
        logger.warning(f"Unknown filter operator '{op}', defaulting to 'eq'")
        op = "eq"
    
    c["operator"] = op
    
    # Ensure is_implicit is boolean
    if "is_implicit" in c:
        c["is_implicit"] = bool(c["is_implicit"])
    else:
        c["is_implicit"] = False
    
    return c


def _sanitize_aggregate(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sanitize aggregate constraint."""
    # Normalize function
    func = c.get("function", "").lower().strip()
    
    if func not in VALID_AGGREGATE_FUNCTIONS:
        # Common variations
        if func in ("total", "add"):
            func = "sum"
        elif func in ("average", "mean"):
            func = "avg"
        elif func in ("cnt", "number"):
            func = "count"
        elif func in ("minimum", "lowest"):
            func = "min"
        elif func in ("maximum", "highest"):
            func = "max"
        else:
            logger.warning(f"Unknown aggregate function '{func}', defaulting to 'count'")
            func = "count"
    
    c["function"] = func
    
    # Ensure column exists
    if not c.get("column"):
        c["column"] = "*"
    
    return c


def _sanitize_existence(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sanitize existence constraint."""
    # Ensure required fields
    if not c.get("related_table"):
        logger.warning("Existence constraint missing 'related_table', skipping")
        return None
    if not c.get("join_condition"):
        c["join_condition"] = "id = id"  # Placeholder
    
    # Ensure exists is boolean
    if "exists" in c:
        c["exists"] = bool(c["exists"])
    else:
        c["exists"] = True
    
    return c


def _sanitize_uniqueness(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sanitize uniqueness constraint."""
    # Ensure columns is a list
    columns = c.get("columns", [])
    if isinstance(columns, str):
        columns = [columns]
    elif not isinstance(columns, list):
        columns = []
    
    if not columns:
        # Try alternative field names
        col = c.get("column") or c.get("field")
        if col:
            columns = [col] if isinstance(col, str) else list(col)
    
    if not columns:
        logger.warning("Uniqueness constraint missing 'columns', skipping")
        return None
    
    c["columns"] = columns
    return c


def sanitize_spec_json(raw_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a raw ConstraintSpec dict from LLM output.
    
    Fixes common issues:
    - Normalizes constraint types and operators
    - Adds missing default fields
    - Removes invalid constraints gracefully
    """
    result = {}
    
    # scope_table is required
    result["scope_table"] = raw_spec.get("scope_table") or raw_spec.get("table") or "unknown"
    
    # Optional fields
    if raw_spec.get("scope_description"):
        result["scope_description"] = str(raw_spec["scope_description"])
    if raw_spec.get("raw_query"):
        result["raw_query"] = str(raw_spec["raw_query"])
    if raw_spec.get("confidence"):
        try:
            result["confidence"] = float(raw_spec["confidence"])
        except (ValueError, TypeError):
            pass
    
    # Process constraints
    raw_constraints = raw_spec.get("constraints", [])
    if not isinstance(raw_constraints, list):
        raw_constraints = [raw_constraints] if raw_constraints else []
    
    sanitized_constraints = []
    for constraint in raw_constraints:
        sanitized = sanitize_constraint(constraint)
        if sanitized:
            sanitized_constraints.append(sanitized)
    
    result["constraints"] = sanitized_constraints
    
    return result


def parse_spec_safely(
    text: str, 
    fallback_table: str = "unknown"
) -> ConstraintSpec:
    """
    Parse LLM output text into a ConstraintSpec with robust error handling.
    
    Returns a valid ConstraintSpec even if parsing fails (with empty constraints).
    """
    try:
        # Step 1: Extract JSON from text
        raw_json = parse_json_from_text(text)
        
        # Step 2: Sanitize the JSON
        sanitized = sanitize_spec_json(raw_json)
        
        # Step 3: Create ConstraintSpec (may still fail on edge cases)
        return ConstraintSpec(**sanitized)
        
    except Exception as e:
        logger.warning(f"Failed to parse spec, returning empty spec: {e}")
        # Return a minimal valid spec
        return ConstraintSpec(
            scope_table=fallback_table,
            constraints=[],
            scope_description=f"Parse failed: {str(e)[:100]}"
        )


def validate_spec(spec: ConstraintSpec) -> List[str]:
    """
    Validate a ConstraintSpec and return a list of warnings/errors.
    Returns empty list if valid.
    """
    issues = []
    
    if not spec.scope_table or spec.scope_table == "unknown":
        issues.append("scope_table is missing or unknown")
    
    if not spec.constraints:
        issues.append("No constraints defined (empty spec)")
    
    for i, c in enumerate(spec.constraints):
        if isinstance(c, FilterDSL):
            if not c.field:
                issues.append(f"Constraint {i}: filter missing field")
        elif isinstance(c, TemporalConstraint):
            if c.constraint_type == "quarter" and not c.quarter:
                issues.append(f"Constraint {i}: quarter constraint missing quarter value")
        elif isinstance(c, AggregateConstraint):
            if not c.column:
                issues.append(f"Constraint {i}: aggregate missing column")
    
    return issues
