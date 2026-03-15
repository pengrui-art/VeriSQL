"""
Fault Localizer Module

Core contribution C3: Counterexample-Guided Structured Repair.

Given a verification failure (counterexample from Z3 or violation from dynamic verifier),
this module localizes the fault to specific SQL clause(s) and generates structured
PatchActions for the repair node.

Pipeline:
    VerificationResult → FaultLocalizer → [FaultLocalization, ...] → PatchActions
    
The key insight: instead of passing vague text feedback ("fix the date filter"),
we generate PRECISE, clause-level repair instructions that the SQL generator
can mechanically apply.
"""

import re
import logging
from typing import List, Optional, Dict, Any, Tuple

import sqlglot
from sqlglot import exp

from verisql.agents.state import (
    VerificationResult,
    FaultLocalization,
    PatchAction,
    PatchActionType,
)
from verisql.core.dsl import (
    ConstraintSpec,
    FilterDSL,
    TemporalConstraint,
    AggregateConstraint,
    QUARTER_DATE_RANGES,
)

logger = logging.getLogger(__name__)


class FaultLocalizer:
    """
    Localizes verification failures to SQL clause level and generates PatchActions.
    
    Algorithm:
    1. Parse SQL into AST using sqlglot
    2. For each violated Spec constraint:
       a. Search the SQL AST for a corresponding predicate
       b. If not found → MISSING fault → ADD_PREDICATE patch
       c. If found but value mismatch → INCORRECT/BOUNDARY fault → FIX_BOUNDARY/FIX_COLUMN patch  
    3. Return ordered list of FaultLocalizations with PatchActions
    """
    
    def __init__(self, dialect: str = "sqlite"):
        self.dialect = dialect
    
    def localize(
        self,
        sql: str,
        spec: ConstraintSpec,
        verification_result: VerificationResult,
    ) -> List[FaultLocalization]:
        """
        Main entry point: localize faults from verification result.
        
        Args:
            sql: The SQL query that failed verification
            spec: The constraint specification it was verified against
            verification_result: The result containing counterexample/violations
            
        Returns:
            List of FaultLocalization objects with patch actions
        """
        if verification_result.status == "PASS":
            return []
        
        faults = []
        
        # Parse SQL AST
        try:
            ast = sqlglot.parse(sql, dialect=self.dialect)[0]
        except Exception as e:
            logger.warning(f"Failed to parse SQL for fault localization: {e}")
            # Fallback: generate generic fault
            return [self._generic_fault(verification_result)]
        
        # Extract existing WHERE predicates from SQL
        sql_predicates = self._extract_predicates(ast)
        
        # For each spec constraint, check if SQL properly implements it
        for constraint in spec.constraints:
            fault = self._localize_constraint(
                constraint, sql_predicates, ast, sql, verification_result
            )
            if fault:
                faults.append(fault)
        
        # If we found no specific faults but verification failed,
        # generate a generic fault from the verification message
        if not faults and verification_result.status == "FAIL":
            faults.append(self._generic_fault(verification_result))
        
        return faults
    
    def _extract_predicates(self, ast) -> List[Dict[str, Any]]:
        """Extract all WHERE clause predicates from the SQL AST."""
        predicates = []
        
        where = ast.find(exp.Where)
        if not where:
            return predicates
        
        self._walk_predicates(where.this, predicates)
        return predicates
    
    def _walk_predicates(self, expr, predicates: List[Dict[str, Any]]):
        """Recursively walk expression tree to extract predicates."""
        if isinstance(expr, exp.And):
            self._walk_predicates(expr.left, predicates)
            self._walk_predicates(expr.right, predicates)
        elif isinstance(expr, exp.Or):
            # Treat OR branches as a single composite
            self._walk_predicates(expr.left, predicates)
            self._walk_predicates(expr.right, predicates)
        elif isinstance(expr, (exp.EQ, exp.NEQ, exp.GT, exp.LT, exp.GTE, exp.LTE)):
            pred = self._comparison_to_dict(expr)
            if pred:
                predicates.append(pred)
        elif isinstance(expr, exp.Between):
            predicates.append({
                "type": "between",
                "column": self._get_column_name(expr.this),
                "low": str(expr.args.get("low")),
                "high": str(expr.args.get("high")),
                "raw_expr": expr,
            })
        elif isinstance(expr, exp.In):
            predicates.append({
                "type": "in",
                "column": self._get_column_name(expr.this),
                "values": [str(v) for v in expr.expressions],
                "raw_expr": expr,
            })
        elif isinstance(expr, exp.Not):
            # Handle NOT(expr)
            self._walk_predicates(expr.this, predicates)
        elif isinstance(expr, exp.Like):
            predicates.append({
                "type": "like",
                "column": self._get_column_name(expr.this),
                "value": str(expr.expression),
                "raw_expr": expr,
            })
    
    def _comparison_to_dict(self, expr) -> Optional[Dict[str, Any]]:
        """Convert a comparison expression to a dict."""
        op_map = {
            exp.EQ: "eq",
            exp.NEQ: "neq",
            exp.GT: "gt",
            exp.LT: "lt",
            exp.GTE: "gte",
            exp.LTE: "lte",
        }
        
        op = op_map.get(type(expr))
        if not op:
            return None
        
        return {
            "type": op,
            "column": self._get_column_name(expr.left),
            "value": self._get_literal_value(expr.right),
            "raw_expr": expr,
        }
    
    def _get_column_name(self, node) -> str:
        """Extract clean column name from AST node."""
        if isinstance(node, exp.Column):
            return node.this.name if hasattr(node.this, 'name') else str(node.this)
        return str(node).strip("'\"").split(".")[-1]
    
    def _get_literal_value(self, node) -> str:
        """Extract literal value from AST node."""
        s = str(node).strip("'\"")
        return s
    
    # ============== Constraint-Level Localization ==============
    
    def _localize_constraint(
        self,
        constraint,
        sql_predicates: List[Dict[str, Any]],
        ast,
        sql: str,
        verification_result: VerificationResult,
    ) -> Optional[FaultLocalization]:
        """Localize a single spec constraint against SQL predicates."""
        
        if isinstance(constraint, FilterDSL):
            return self._localize_filter(constraint, sql_predicates, sql, verification_result)
        elif isinstance(constraint, TemporalConstraint):
            return self._localize_temporal(constraint, sql_predicates, sql, verification_result)
        elif isinstance(constraint, AggregateConstraint):
            return self._localize_aggregate(constraint, ast, sql, verification_result)
        
        return None
    
    def _localize_filter(
        self,
        constraint: FilterDSL,
        sql_predicates: List[Dict[str, Any]],
        sql: str,
        verification_result: VerificationResult,
    ) -> Optional[FaultLocalization]:
        """Localize a filter constraint violation."""
        
        target_col = constraint.field.lower()
        target_op = constraint.operator
        target_val = str(constraint.value).strip("'\"").lower()
        
        # Search for matching predicate in SQL
        matching_pred = None
        for pred in sql_predicates:
            pred_col = pred.get("column", "").lower()
            if pred_col == target_col:
                matching_pred = pred
                break
        
        if matching_pred is None:
            # MISSING: No predicate for this column at all
            suggested = self._build_filter_sql(constraint)
            
            # Build reason from counterexample
            reason = f"SQL has no filter on '{constraint.field}'"
            if verification_result.counterexample:
                ce = verification_result.counterexample
                reason += f". Counterexample: a row with {ce} passes SQL but violates Spec"
            
            return FaultLocalization(
                violated_constraint=f"{constraint.field} {constraint.operator} {constraint.value}",
                counterexample=verification_result.counterexample,
                sql_clause="WHERE",
                fault_type="MISSING",
                patch_actions=[
                    PatchAction(
                        action_type=PatchActionType.ADD_PREDICATE,
                        target_clause="WHERE",
                        current_fragment="",
                        suggested_fragment=suggested,
                        reason=reason,
                        confidence=0.9,
                    )
                ],
            )
        
        # Found a predicate on this column — check if it's correct
        pred_op = matching_pred.get("type", "")
        pred_val = str(matching_pred.get("value", "")).strip("'\"").lower()
        
        # Check operator mismatch
        if pred_op != target_op:
            return self._build_incorrect_fault(
                constraint, matching_pred, verification_result,
                issue=f"operator mismatch: SQL uses '{pred_op}' but Spec requires '{target_op}'"
            )
        
        # Check value mismatch
        if pred_val != target_val:
            return self._build_incorrect_fault(
                constraint, matching_pred, verification_result,
                issue=f"value mismatch: SQL uses '{pred_val}' but Spec requires '{target_val}'"
            )
        
        return None  # Predicate matches, no fault
    
    def _localize_temporal(
        self,
        constraint: TemporalConstraint,
        sql_predicates: List[Dict[str, Any]],
        sql: str,
        verification_result: VerificationResult,
    ) -> Optional[FaultLocalization]:
        """Localize a temporal constraint violation."""
        
        target_col = constraint.column.lower()
        
        # Compute expected date range
        expected_start, expected_end = self._get_temporal_range(constraint)
        if not expected_start or not expected_end:
            return None
        
        # Search for date-related predicates on the column
        date_preds = [
            p for p in sql_predicates
            if p.get("column", "").lower() == target_col
        ]
        
        if not date_preds:
            # MISSING: No temporal filter at all
            suggested = (
                f"{constraint.column} BETWEEN '{expected_start}' AND '{expected_end}'"
            )
            
            return FaultLocalization(
                violated_constraint=f"Temporal: {constraint.column} in [{expected_start}, {expected_end}]",
                counterexample=verification_result.counterexample,
                sql_clause="WHERE",
                fault_type="MISSING",
                patch_actions=[
                    PatchAction(
                        action_type=PatchActionType.ADD_PREDICATE,
                        target_clause="WHERE",
                        current_fragment="",
                        suggested_fragment=suggested,
                        reason=f"SQL has no date filter on '{constraint.column}'. "
                               f"Expected range: {expected_start} to {expected_end}",
                        confidence=0.9,
                    )
                ],
            )
        
        # Check for BETWEEN predicates
        for pred in date_preds:
            if pred["type"] == "between":
                low = pred.get("low", "").strip("'\"")
                high = pred.get("high", "").strip("'\"")
                
                if low != expected_start or high != expected_end:
                    # BOUNDARY: dates don't match expected
                    current_frag = f"{target_col} BETWEEN '{low}' AND '{high}'"
                    suggested_frag = f"{target_col} BETWEEN '{expected_start}' AND '{expected_end}'"
                    
                    return FaultLocalization(
                        violated_constraint=f"Temporal: {constraint.column} in [{expected_start}, {expected_end}]",
                        counterexample=verification_result.counterexample,
                        sql_clause="WHERE",
                        fault_type="BOUNDARY",
                        patch_actions=[
                            PatchAction(
                                action_type=PatchActionType.FIX_BOUNDARY,
                                target_clause="WHERE",
                                current_fragment=current_frag,
                                suggested_fragment=suggested_frag,
                                reason=f"Boundary error: SQL uses [{low}, {high}] but "
                                       f"Spec requires [{expected_start}, {expected_end}]",
                                confidence=0.85,
                            )
                        ],
                    )
        
        # Check individual comparison predicates for boundary issues
        for pred in date_preds:
            if pred["type"] in ("gte", "gt", "lte", "lt"):
                pred_val = pred.get("value", "").strip("'\"")
                
                # Check for off-by-one boundary errors
                if pred["type"] == "gte" and pred_val != expected_start:
                    return self._build_boundary_fault(
                        constraint, pred, expected_start, "start", verification_result
                    )
                elif pred["type"] == "gt":
                    # > should often be >= for inclusive ranges
                    return FaultLocalization(
                        violated_constraint=f"Temporal: {constraint.column} >= {expected_start}",
                        counterexample=verification_result.counterexample,
                        sql_clause="WHERE",
                        fault_type="BOUNDARY",
                        patch_actions=[
                            PatchAction(
                                action_type=PatchActionType.FIX_BOUNDARY,
                                target_clause="WHERE",
                                current_fragment=f"{target_col} > '{pred_val}'",
                                suggested_fragment=f"{target_col} >= '{expected_start}'",
                                reason=f"Boundary error: '>' excludes the start date. "
                                       f"Use '>=' for inclusive range.",
                                confidence=0.85,
                            )
                        ],
                    )
        
        return None
    
    def _localize_aggregate(
        self,
        constraint: AggregateConstraint,
        ast,
        sql: str,
        verification_result: VerificationResult,
    ) -> Optional[FaultLocalization]:
        """Localize an aggregate constraint violation."""
        
        # Check if appropriate aggregate function is in SQL
        sql_upper = sql.upper()
        target_func = constraint.function.upper()
        target_col = constraint.column.lower()
        
        has_aggregate = target_func in sql_upper
        
        if not has_aggregate:
            return FaultLocalization(
                violated_constraint=f"Aggregate: {target_func}({constraint.column})",
                counterexample=verification_result.counterexample,
                sql_clause="SELECT",
                fault_type="MISSING",
                patch_actions=[
                    PatchAction(
                        action_type=PatchActionType.FIX_AGGREGATION,
                        target_clause="SELECT",
                        current_fragment="",
                        suggested_fragment=f"{target_func}({constraint.column})",
                        reason=f"SQL does not use {target_func}() on '{constraint.column}' "
                               f"as required by Spec",
                        confidence=0.7,
                    )
                ],
            )
        
        return None
    
    # ============== Helper Methods ==============
    
    def _get_temporal_range(self, constraint: TemporalConstraint) -> Tuple[str, str]:
        """Get expected date range from temporal constraint."""
        if constraint.constraint_type == "quarter" and constraint.quarter:
            year = constraint.year or 2024
            start_suffix, end_suffix = QUARTER_DATE_RANGES.get(
                constraint.quarter, ("01-01", "12-31")
            )
            return f"{year}-{start_suffix}", f"{year}-{end_suffix}"
        
        if constraint.constraint_type == "date_range":
            return str(constraint.start_date or ""), str(constraint.end_date or "")
        
        if constraint.constraint_type == "year" and constraint.year:
            return f"{constraint.year}-01-01", f"{constraint.year}-12-31"
        
        return "", ""
    
    def _build_filter_sql(self, constraint: FilterDSL) -> str:
        """Build SQL fragment for a filter constraint."""
        op_map = {
            "eq": "=", "neq": "!=", "gt": ">", "lt": "<",
            "gte": ">=", "lte": "<=", "like": "LIKE",
        }
        
        sql_op = op_map.get(constraint.operator, "=")
        val = constraint.value
        
        if isinstance(val, str):
            return f"{constraint.field} {sql_op} '{val}'"
        return f"{constraint.field} {sql_op} {val}"
    
    def _build_incorrect_fault(
        self,
        constraint: FilterDSL,
        matching_pred: Dict[str, Any],
        verification_result: VerificationResult,
        issue: str,
    ) -> FaultLocalization:
        """Build fault for an incorrect (but present) predicate."""
        suggested = self._build_filter_sql(constraint)
        raw = matching_pred.get("raw_expr")
        current = str(raw) if raw else ""
        
        return FaultLocalization(
            violated_constraint=f"{constraint.field} {constraint.operator} {constraint.value}",
            counterexample=verification_result.counterexample,
            sql_clause="WHERE",
            fault_type="INCORRECT",
            patch_actions=[
                PatchAction(
                    action_type=PatchActionType.FIX_BOUNDARY if "boundary" in issue.lower()
                                else PatchActionType.FIX_COLUMN,
                    target_clause="WHERE",
                    current_fragment=current,
                    suggested_fragment=suggested,
                    reason=f"Predicate {issue}",
                    confidence=0.85,
                )
            ],
        )
    
    def _build_boundary_fault(
        self,
        constraint: TemporalConstraint,
        pred: Dict[str, Any],
        expected_val: str,
        bound_type: str,
        verification_result: VerificationResult,
    ) -> FaultLocalization:
        """Build fault for a temporal boundary error."""
        col = constraint.column
        pred_val = str(pred.get("value", "")).strip("'\"")
        pred_op = pred["type"]
        
        op_map = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<"}
        expected_sql_op = ">=" if bound_type == "start" else "<="
        
        return FaultLocalization(
            violated_constraint=f"Temporal: {col} {expected_sql_op} '{expected_val}'",
            counterexample=verification_result.counterexample,
            sql_clause="WHERE",
            fault_type="BOUNDARY",
            patch_actions=[
                PatchAction(
                    action_type=PatchActionType.FIX_BOUNDARY,
                    target_clause="WHERE",
                    current_fragment=f"{col} {op_map.get(pred_op, pred_op)} '{pred_val}'",
                    suggested_fragment=f"{col} {expected_sql_op} '{expected_val}'",
                    reason=f"Boundary error on {bound_type} date: "
                           f"SQL uses '{pred_val}' but Spec requires '{expected_val}'",
                    confidence=0.85,
                )
            ],
        )
    
    def _generic_fault(self, verification_result: VerificationResult) -> FaultLocalization:
        """Fallback: generic fault when specific localization fails."""
        return FaultLocalization(
            violated_constraint=verification_result.message,
            counterexample=verification_result.counterexample,
            sql_clause="UNKNOWN",
            fault_type="MISSING",
            patch_actions=[
                PatchAction(
                    action_type=PatchActionType.ADD_PREDICATE,
                    target_clause="WHERE",
                    current_fragment="",
                    suggested_fragment="<requires manual analysis>",
                    reason=verification_result.message,
                    confidence=0.3,
                )
            ],
        )


def format_patch_actions(faults: List[FaultLocalization]) -> str:
    """
    Format fault localizations into structured text for the SQL generator prompt.
    
    This replaces the old free-text feedback with a deterministic, parseable format:
    
    [PATCH-1] ADD_PREDICATE in WHERE:
      + Add: status != 'cancelled'
      Reason: Counterexample {status: 'cancelled'} passes SQL but violates Spec.
    """
    if not faults:
        return ""
    
    lines = ["=== STRUCTURED REPAIR INSTRUCTIONS ==="]
    patch_num = 0
    
    for fault in faults:
        for action in fault.patch_actions:
            patch_num += 1
            lines.append(f"\n[PATCH-{patch_num}] {action.action_type.value} in {action.target_clause}:")
            
            if action.current_fragment:
                lines.append(f"  - Current: {action.current_fragment}")
            
            lines.append(f"  + Fix to: {action.suggested_fragment}")
            lines.append(f"  Reason: {action.reason}")
            lines.append(f"  Confidence: {action.confidence:.0%}")
    
    lines.append("\n=== END REPAIR INSTRUCTIONS ===")
    return "\n".join(lines)
