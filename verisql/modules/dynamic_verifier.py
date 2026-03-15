"""
Hybrid Verification Engine (Dynamic Component)

This module implements the dynamic half of VeriSQL's Hybrid Verification architecture.
It synthesizes adversarial mock data based on formal specifications (ConstraintSpec)
and executes the generated SQL in a sandboxed SQLite environment to detect
behavioral violations (e.g., data-specific edge cases) that static analysis might miss.

Core C2 Innovation:
- Constraint-driven micro-DB synthesis (not random data)
- Z3-model-driven adversarial rows from static counterexamples
- Boundary value testing at spec constraint edges

Components:
1. MockDBGenerator: Synthesizes micro-databases with "edge case" data.
2. SandboxExecutor: Runs SQL on in-memory SQLite.
3. DynamicVerifier: Orchestrates the verification logic.
"""

import sqlite3
import pandas as pd
import numpy as np
import datetime
import re
from typing import Dict, List, Any, Optional, Tuple
import logging

from verisql.core.dsl import ConstraintSpec, TemporalConstraint, FilterDSL
from verisql.agents.state import VerificationResult
from verisql.core.dsl import QUARTER_DATE_RANGES

logger = logging.getLogger(__name__)


class MockDBGenerator:
    """
    Synthesizes a minimal "micro-database" for adversarial testing.

    Strategy:
    1. Identify columns constrained by the Spec.
    2. Generate specific values that SATISFY the spec.
    3. Generate specific values that VIOLATE the spec (Adversarial Data).
    4. Construct a DataFrame containing both types of rows.
    """

    def __init__(self, schema_info: Dict[str, Any]):
        self.schema_info = schema_info

    def generate(self, spec: ConstraintSpec) -> Dict[str, pd.DataFrame]:
        """Generate mock tables for the given specification."""
        tables_data = {}
        scope_table = spec.scope_table.lower()

        # We focus primarily on the scope table for now
        # In a real system, we'd traverse joins found in SchemaInfo

        # 1. Identify critical columns and their constraints
        columns_config = self._analyze_constraints(spec)

        # 2. Generate rows
        # Row 1: The "Golden Row" - Satisfies ALL constraints
        golden_row = self._generate_row(columns_config, mode="satisfy")

        rows = [golden_row]

        # Rows 2..N: "Adversarial Rows" - Violate one constraint at a time
        for constraint_idx in range(len(spec.constraints)):
            # Only generate adversarial rows for filters and temporal constraints
            # Aggregates don't easily map to single-row violations in this simple logic
            c = spec.constraints[constraint_idx]
            if c.type in ["filter", "temporal"]:
                adv_row = self._generate_row(
                    columns_config, mode="violate", target_constraint_idx=constraint_idx
                )
                if adv_row:
                    rows.append(adv_row)

        # 3. Create DataFrame
        df = pd.DataFrame(rows)

        # Ensure all columns from schema (at least minimal set) are present
        # This prevents "no such column" errors for unconstrained columns selected in SQL
        if "tables" in self.schema_info and scope_table in self.schema_info["tables"]:
            for col_def in self.schema_info["tables"][scope_table]:
                # col_def can be a dict: {'name': '...', 'type': '...'} or a string
                if isinstance(col_def, dict):
                    col_name = col_def["name"]
                elif isinstance(col_def, str):
                    col_name = col_def
                else:
                    continue
                if col_name not in df.columns:
                    df[col_name] = "mock_val"  # Fill defaults

        tables_data[scope_table] = df
        return tables_data

    def generate_from_z3_model(
        self, spec: ConstraintSpec, z3_counterexample: Dict[str, str]
    ) -> Dict[str, pd.DataFrame]:
        """
        Generate mock DB using Z3 counterexample model as the adversarial row.
        
        This is the Z3-model-driven synthesis: instead of heuristic value generation,
        we take the concrete variable assignments from the Z3 counterexample and
        reverse-engineer them into a database row.
        
        Args:
            spec: The constraint specification
            z3_counterexample: Dict from Z3 model, e.g. {'status': '"cancelled"', 'amount': '150'}
            
        Returns:
            Mock database tables with the Z3 counterexample as an adversarial row
        """
        tables_data = {}
        scope_table = spec.scope_table.lower()
        
        # 1. Generate the "Golden Row" (satisfies all constraints) as baseline
        columns_config = self._analyze_constraints(spec)
        golden_row = self._generate_row(columns_config, mode="satisfy")
        
        # 2. Build adversarial row from Z3 counterexample
        adversarial_row = {}
        for z3_var, z3_val in z3_counterexample.items():
            # Z3 variable names may have suffixes like '_as_int'
            col_name = z3_var.replace('_as_int', '')
            
            # Clean Z3 value representation
            clean_val = str(z3_val).strip('"').strip("'")
            
            # Convert _as_int values back to dates if needed
            if z3_var.endswith('_as_int') and clean_val.isdigit() and len(clean_val) == 8:
                # Convert YYYYMMDD int back to YYYY-MM-DD date string
                clean_val = f"{clean_val[:4]}-{clean_val[4:6]}-{clean_val[6:8]}"
            
            adversarial_row[col_name] = clean_val
        
        # 3. Fill missing columns in adversarial row with golden values
        for col, val in golden_row.items():
            if col not in adversarial_row:
                adversarial_row[col] = val
        
        rows = [golden_row, adversarial_row]
        
        # 4. Also add heuristic adversarial rows for comprehensive coverage
        for constraint_idx in range(len(spec.constraints)):
            c = spec.constraints[constraint_idx]
            if c.type in ["filter", "temporal"]:
                adv_row = self._generate_row(
                    columns_config, mode="violate", target_constraint_idx=constraint_idx
                )
                if adv_row and adv_row not in rows:
                    rows.append(adv_row)
        
        df = pd.DataFrame(rows)
        
        # Fill schema columns
        if "tables" in self.schema_info and scope_table in self.schema_info["tables"]:
            for col_def in self.schema_info["tables"][scope_table]:
                if isinstance(col_def, dict):
                    col_name = col_def["name"]
                elif isinstance(col_def, str):
                    col_name = col_def
                else:
                    continue
                if col_name not in df.columns:
                    df[col_name] = "mock_val"
        
        tables_data[scope_table] = df
        return tables_data

    def _analyze_constraints(self, spec: ConstraintSpec) -> Dict[str, Any]:
        """
        Parses spec to determine valid/invalid values for each constrained column.
        Returns a dict: {col_name: {'valid': val, 'invalid': val}}
        """
        config = {}

        for idx, c in enumerate(spec.constraints):
            if c.type == "filter":
                col = c.field
                if col not in config:
                    config[col] = {"constraints": []}
                config[col]["constraints"].append((idx, c))

            elif c.type == "temporal":
                col = c.column
                if col not in config:
                    config[col] = {"constraints": []}
                config[col]["constraints"].append((idx, c))

        return config

    def _generate_row(
        self,
        config: Dict[str, Any],
        mode: str = "satisfy",
        target_constraint_idx: int = -1,
    ) -> Dict[str, Any]:
        """
        Generates a single row.
        mode="satisfy": All columns satisfy their constraints.
        mode="violate": The target_constraint is violated; others are satisfied.
        """
        row = {}

        for col, info in config.items():
            # Default valid value
            val = "valid_default"

            # Check applicable constraints for this column
            for c_idx, constraint in info["constraints"]:

                should_violate = mode == "violate" and c_idx == target_constraint_idx

                if constraint.type == "filter":
                    val = self._get_filter_value(constraint, violate=should_violate)

                elif constraint.type == "temporal":
                    val = self._get_temporal_value(constraint, violate=should_violate)

            row[col] = val

        return row

    def _get_filter_value(self, c: FilterDSL, violate: bool) -> Any:
        """Get a value that strictly satisfies or violates a Filter constraint.
        
        Full operator coverage for constraint-driven value generation.
        """
        op = c.operator
        val = c.value

        if op == "eq":
            return self._mutate(val) if violate else val
        elif op == "neq":
            return val if violate else self._mutate(val)
        elif op == "gt":  # > value
            try:
                base = float(val)
                return base if violate else (base + 1)  # boundary: equal (violates >) vs +1 (satisfies)
            except (ValueError, TypeError):
                return 0 if violate else val
        elif op == "lt":  # < value
            try:
                base = float(val)
                return base if violate else (base - 1)
            except (ValueError, TypeError):
                return val if violate else 0
        elif op == "gte":  # >= value
            try:
                base = float(val)
                return (base - 1) if violate else base  # boundary: -1 (violates >=) vs equal (satisfies)
            except (ValueError, TypeError):
                return 0 if violate else val
        elif op == "lte":  # <= value
            try:
                base = float(val)
                return (base + 1) if violate else base
            except (ValueError, TypeError):
                return val if violate else 0
        elif op == "in":
            # value should be a list
            if isinstance(val, list) and len(val) > 0:
                return self._mutate(val[0]) if violate else val[0]
            return "not_in_list" if violate else val
        elif op == "not_in":
            if isinstance(val, list) and len(val) > 0:
                return val[0] if violate else self._mutate(val[0])
            return val if violate else "safe_val"
        elif op == "like":
            pattern = str(val).strip("'\"")
            if violate:
                return "ZZZZZ_no_match"  # unlikely to match any LIKE pattern
            else:
                # Satisfy: extract core from pattern (remove % wildcards)
                core = pattern.replace("%", "")
                return core if core else "match_val"
        elif op == "is_null":
            return "not_null_val" if violate else None
        elif op == "is_not_null":
            return None if violate else "has_value"
        
        return val

    def _get_temporal_value(self, c: TemporalConstraint, violate: bool) -> str:
        """Get date string satisfying/violating temporal constraint."""
        from datetime import date, timedelta

        def parse_ymd(s: str) -> date:
            y, m, d = s.split("-")
            return date(int(y), int(m), int(d))

        def fmt(dt: date) -> str:
            return dt.isoformat()

        if c.constraint_type == "quarter" and c.quarter:
            year = c.year or 2024
            start_suffix, end_suffix = QUARTER_DATE_RANGES.get(
                c.quarter, ("01-01", "12-31")
            )
            start = parse_ymd(f"{year}-{start_suffix}")
            end = parse_ymd(f"{year}-{end_suffix}")

            if violate:
                # Boundary adversarial case: just outside the range
                return fmt(start - timedelta(days=1))
            # Boundary satisfying case: exact start (catches off-by-one bugs)
            return fmt(start)

        if c.constraint_type == "date_range" and c.start_date and c.end_date:
            start = parse_ymd(str(c.start_date))
            end = parse_ymd(str(c.end_date))
            if violate:
                return fmt(start - timedelta(days=1))
            return fmt(start)

        if c.constraint_type == "year" and c.year:
            y = int(c.year)
            if violate:
                return f"{y-1}-12-31"
            return f"{y}-01-01"

        return "2024-01-01"

    def _mutate(self, val: Any) -> Any:
        """Return a different value."""
        if isinstance(val, str):
            return val + "_mutated"
        if isinstance(val, (int, float)):
            return val + 1
        return val


class SandboxExecutor:
    """Safely executes SQL on in-memory SQLite loaded with mock data."""

    def execute(
        self, sql: str, mock_data: Dict[str, pd.DataFrame]
    ) -> Tuple[List[Dict], str]:
        """
        Returns (rows, error_message).
        rows is a list of dicts. error_message is empty if success.
        """
        try:
            conn = sqlite3.connect(":memory:")

            # Load all mock tables
            for table_name, df in mock_data.items():
                df.to_sql(table_name, conn, index=False)

            cursor = conn.cursor()
            cursor.execute(sql)

            columns = [description[0] for description in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

            conn.close()
            return results, ""

        except Exception as e:
            return [], str(e)


class DynamicVerifier:
    """Main entry point for Dynamic Verification."""

    def __init__(self, schema_info: Dict[str, Any]):
        self.mock_gen = MockDBGenerator(schema_info)
        self.executor = SandboxExecutor()

    def verify(
        self,
        sql: str,
        spec: ConstraintSpec,
        z3_counterexample: Optional[Dict[str, str]] = None,
    ) -> VerificationResult:
        """
        Performs dynamic verification.

        1. Synthesize Mock DB (Golden Row + Adversarial Rows).
           - If Z3 counterexample available, use it for Z3-model-driven synthesis.
        2. Execute SQL.
        3. Check:
           - Did execution fail? (SQL Error)
           - Did result contain 'Adversarial Rows'? (Logic Error)
             (If Spec restricts X, but SQL returns X, that's a failure)
        """
        # 1. Synthesis
        try:
            if z3_counterexample:
                # Z3-model-driven synthesis: use counterexample as adversarial row
                mock_db = self.mock_gen.generate_from_z3_model(spec, z3_counterexample)
            else:
                # Heuristic synthesis: generate boundary values from constraints
                mock_db = self.mock_gen.generate(spec)
        except Exception as e:
            logger.warning(f"Mock Data Gen failed: {e}")
            return VerificationResult(status="SKIP", message="Mock Data Gen failed")

        # 2. Execution
        rows, error = self.executor.execute(sql, mock_db)

        if error:
            # If SQL implies valid syntax but fails on data (e.g. type mismatch), it's a FAIL
            # But mostly this catches runtime errors
            return VerificationResult(
                status="FAIL", message=f"Sandbox Execution Error: {error}"
            )

        # 3. Validation Logic
        # Heuristic:
        # The Mock DB contains specific "Adversarial Rows" designed to violate specific filters.
        # If the SQL returns these rows, it means the SQL filter is missing or too loose.

        # How do we know which rows are adversarial?
        # A simple way: Re-evaluate constraints on the RESULT rows in Python.
        # If any result row violates the Spec, the SQL failed to filter it.

        violations = []
        for i, row in enumerate(rows):
            is_valid, reason = self._check_row_against_spec(row, spec)
            if not is_valid:
                violations.append(f"Row {i} violates spec: {reason}. Row data: {row}")

        if violations:
            return VerificationResult(
                status="FAIL",
                message="Dynamic Verification Failed: SQL returned data that violates Spec.",
                missing_constraints=violations[:3],  # Return top 3 violations
            )

        return VerificationResult(status="PASS", message="Dynamic Verification Passed")

    def _check_row_against_spec(
        self, row: Dict[str, Any], spec: ConstraintSpec
    ) -> Tuple[bool, str]:
        """Checks if a single result row satisfies the constraints."""
        for c in spec.constraints:

            if c.type == "filter":
                # Check if column exists in result (might be aliased or not selected)
                # If not selected, we can't verify it dynamically! This is a limitation.
                # But typically SELECT * or SELECT status...

                col = c.field
                if col in row:  # Only check if present
                    val = row[col]
                    if not self._check_filter(val, c):
                        return (
                            False,
                            f"Filter {col} {c.operator} {c.value} failed on value '{val}'",
                        )

            elif c.type == "temporal":
                col = c.column
                if col in row:
                    val = row[col]
                    if not self._check_temporal(val, c):
                        return (
                            False,
                            f"Temporal {c.constraint_type} failed on value '{val}'",
                        )

        return True, ""

    def _check_filter(self, val: Any, c: FilterDSL) -> bool:
        """Check if a value satisfies a filter constraint. Full operator coverage."""
        target = c.value
        op = c.operator

        if op == "eq":
            return str(val).strip().lower() == str(target).strip().lower()
        if op == "neq":
            return str(val).strip().lower() != str(target).strip().lower()
        
        # Numeric comparisons
        try:
            num_val = float(val)
            num_target = float(target)
            if op == "gt":
                return num_val > num_target
            if op == "lt":
                return num_val < num_target
            if op == "gte":
                return num_val >= num_target
            if op == "lte":
                return num_val <= num_target
        except (ValueError, TypeError):
            # If not numeric, do string comparison for ordering ops
            if op in ("gt", "gte", "lt", "lte"):
                s_val = str(val).strip().lower()
                s_target = str(target).strip().lower()
                if op == "gt":
                    return s_val > s_target
                if op == "lt":
                    return s_val < s_target
                if op == "gte":
                    return s_val >= s_target
                if op == "lte":
                    return s_val <= s_target
        
        # Set membership
        if op == "in":
            if isinstance(target, list):
                return str(val).strip().lower() in [str(t).strip().lower() for t in target]
            return str(val).strip().lower() == str(target).strip().lower()
        if op == "not_in":
            if isinstance(target, list):
                return str(val).strip().lower() not in [str(t).strip().lower() for t in target]
            return str(val).strip().lower() != str(target).strip().lower()
        
        # Pattern matching
        if op == "like":
            pattern = str(target).replace("%", ".*").replace("_", ".")
            return bool(re.match(pattern, str(val), re.IGNORECASE))
        
        # Null checks
        if op == "is_null":
            return val is None or str(val).strip().lower() in ('none', 'null', '')
        if op == "is_not_null":
            return val is not None and str(val).strip().lower() not in ('none', 'null', '')
        
        return True  # Unknown operator, pass by default

    def _check_temporal(self, val: str, c: TemporalConstraint) -> bool:
        s = str(val)
        if c.constraint_type == "quarter" and c.quarter:
            year = c.year or 2024
            start_suffix, end_suffix = QUARTER_DATE_RANGES.get(
                c.quarter, ("01-01", "12-31")
            )
            start = f"{year}-{start_suffix}"
            end = f"{year}-{end_suffix}"
            return start <= s <= end

        if c.constraint_type == "date_range" and c.start_date and c.end_date:
            return str(c.start_date) <= s <= str(c.end_date)

        if c.constraint_type == "year" and c.year:
            return s.startswith(f"{int(c.year)}-")

        return True
