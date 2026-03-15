"""
LTL Compiler - Converts DSL to LTL formulas

This is a deterministic compiler that transforms our simplified DSL
into formal LTL (Linear Temporal Logic) formulas for Z3 verification.
No LLM involvement here - pure symbolic transformation.
"""
from typing import List, Tuple
from datetime import datetime

from verisql.core.dsl import (
    ConstraintSpec,
    DSLConstraint,
    TemporalConstraint,
    FilterDSL,
    AggregateConstraint,
    ExistenceConstraint,
    UniquenessConstraint,
    QUARTER_DATE_RANGES,
    OPERATOR_TO_LTL,
)


class LTLFormula:
    """Represents an LTL formula"""
    
    def __init__(self, formula: str, variables: dict = None):
        self.formula = formula
        self.variables = variables or {}
    
    def __str__(self):
        return self.formula
    
    def __repr__(self):
        return f"LTLFormula({self.formula})"
    
    def to_z3_constraints(self) -> List[str]:
        """Convert to Z3 constraint format"""
        # This will be used by the symbolic verifier
        return [self.formula]


class LTLCompiler:
    """
    Compiles DSL constraints to LTL formulas.
    
    Key principle: This is DETERMINISTIC - no LLM, no errors from generation.
    The DSL was designed to be easy to generate correctly.
    """
    
    def __init__(self, current_year: int = None):
        self.current_year = current_year or datetime.now().year
    
    def compile(self, spec: ConstraintSpec) -> LTLFormula:
        """Compile a constraint spec to LTL"""
        formulas = []
        variables = {}
        
        for constraint in spec.constraints:
            formula, vars_ = self._compile_constraint(constraint, spec.scope_table)
            if formula:
                formulas.append(formula)
                variables.update(vars_)
        
        # Combine with AND
        if not formulas:
            combined = "TRUE"
        elif len(formulas) == 1:
            combined = formulas[0]
        else:
            combined = " ∧ ".join(f"({f})" for f in formulas)
        
        # Wrap in FORALL over rows
        final_formula = f"∀row ∈ {spec.scope_table}: ({combined})"
        
        return LTLFormula(final_formula, variables)
    
    def _compile_constraint(
        self, 
        constraint: DSLConstraint,
        table: str
    ) -> Tuple[str, dict]:
        """Compile a single constraint to LTL fragment"""
        
        if isinstance(constraint, TemporalConstraint):
            return self._compile_temporal(constraint)
        elif isinstance(constraint, FilterDSL):
            return self._compile_filter(constraint)
        elif isinstance(constraint, AggregateConstraint):
            return self._compile_aggregate(constraint)
        elif isinstance(constraint, ExistenceConstraint):
            return self._compile_existence(constraint)
        elif isinstance(constraint, UniquenessConstraint):
            return self._compile_uniqueness(constraint)
        else:
            return None, {}
    
    def _compile_temporal(self, c: TemporalConstraint) -> Tuple[str, dict]:
        """Compile temporal constraint"""
        col = c.column
        
        if c.constraint_type == "quarter" and c.quarter:
            # Resolve quarter to date range
            start_suffix, end_suffix = QUARTER_DATE_RANGES.get(c.quarter, ("01-01", "12-31"))
            year = c.year or self.current_year
            start_date = f"{year}-{start_suffix}"
            end_date = f"{year}-{end_suffix}"
            
            formula = f"({col} >= '{start_date}' ∧ {col} <= '{end_date}')"
            return formula, {"temporal_start": start_date, "temporal_end": end_date}
        
        elif c.constraint_type == "date_range":
            formula = f"({col} >= '{c.start_date}' ∧ {col} <= '{c.end_date}')"
            return formula, {"temporal_start": c.start_date, "temporal_end": c.end_date}
        
        elif c.constraint_type == "year" and c.year:
            formula = f"(YEAR({col}) == {c.year})"
            return formula, {"year": c.year}
        
        return None, {}
    
    def _compile_filter(self, c: FilterDSL) -> Tuple[str, dict]:
        """Compile filter constraint"""
        op = OPERATOR_TO_LTL.get(c.operator, c.operator)
        
        # Format value
        if isinstance(c.value, str):
            value_str = f"'{c.value}'"
        elif isinstance(c.value, bool):
            value_str = "TRUE" if c.value else "FALSE"
        elif isinstance(c.value, list):
            value_str = "{" + ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in c.value) + "}"
        elif c.value is None:
            value_str = "NULL"
        else:
            value_str = str(c.value)
        
        # Handle special operators
        if c.operator in ("is_null", "is_not_null"):
            if c.operator == "is_null":
                formula = f"({c.field} IS NULL)"
            else:
                formula = f"({c.field} IS NOT NULL)"
        else:
            formula = f"({c.field} {op} {value_str})"
        
        # Mark if implicit
        if c.is_implicit:
            formula = f"/* IMPLICIT */ {formula}"
        
        return formula, {}
    
    def _compile_aggregate(self, c: AggregateConstraint) -> Tuple[str, dict]:
        """Compile aggregate constraint - mainly for documentation"""
        # Aggregates don't translate directly to LTL row constraints
        # but we track them for SQL verification
        formula = f"/* AGGREGATE: {c.function.upper()}({c.column}) */"
        return formula, {"aggregate": f"{c.function}({c.column})"}
    
    def _compile_existence(self, c: ExistenceConstraint) -> Tuple[str, dict]:
        """Compile existence constraint"""
        if c.exists:
            formula = f"∃r ∈ {c.related_table}: ({c.join_condition})"
        else:
            formula = f"¬∃r ∈ {c.related_table}: ({c.join_condition})"
        return formula, {}
    
    def _compile_uniqueness(self, c: UniquenessConstraint) -> Tuple[str, dict]:
        """Compile uniqueness constraint"""
        cols = ", ".join(c.columns)
        formula = f"UNIQUE({cols})"
        return formula, {}


def compile_to_ltl(spec: ConstraintSpec, year: int = None) -> LTLFormula:
    """Convenience function to compile DSL to LTL"""
    compiler = LTLCompiler(current_year=year)
    return compiler.compile(spec)
