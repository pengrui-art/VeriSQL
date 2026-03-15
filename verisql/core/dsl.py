"""
Constraint DSL (Domain-Specific Language)

A simplified DSL that LLMs generate instead of raw LTL.
This is much easier to generate correctly, then deterministically
compiled to LTL by our compiler.
"""
from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field
from enum import Enum


class ConstraintType(str, Enum):
    """Types of constraints in our DSL"""
    TEMPORAL = "temporal"
    FILTER = "filter"
    AGGREGATE = "aggregate"  
    EXISTENCE = "existence"
    UNIQUENESS = "uniqueness"


# ============== DSL Constraint Definitions ==============

class TemporalConstraint(BaseModel):
    """Temporal constraint - simpler than raw date comparisons"""
    type: Literal["temporal"] = "temporal"
    constraint_type: Literal["date_range", "quarter", "year", "relative"]
    
    # For date_range
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    
    # For quarter/year
    quarter: Optional[str] = None  # "Q1", "Q2", "Q3", "Q4"
    year: Optional[int] = None
    
    # For relative
    relative_expr: Optional[str] = None  # "last_30_days", "this_month"
    
    # Target column
    column: str = "date"


class FilterDSL(BaseModel):
    """Filter constraint in DSL form"""
    type: Literal["filter"] = "filter"
    field: str
    operator: Literal["eq", "neq", "gt", "lt", "gte", "lte", "in", "not_in", "like", "is_null", "is_not_null"]
    value: Union[str, int, float, bool, List[str], None]
    is_implicit: bool = False  # Whether this is an implicit business rule


class AggregateConstraint(BaseModel):
    """Aggregate constraint"""
    type: Literal["aggregate"] = "aggregate"
    function: Literal["sum", "avg", "count", "min", "max"]
    column: str
    alias: Optional[str] = None


class ExistenceConstraint(BaseModel):
    """Existence check constraint"""
    type: Literal["existence"] = "existence"
    exists: bool = True
    related_table: str
    join_condition: str


class UniquenessConstraint(BaseModel):
    """Uniqueness constraint"""
    type: Literal["uniqueness"] = "uniqueness"
    columns: List[str]


DSLConstraint = Union[
    TemporalConstraint,
    FilterDSL,
    AggregateConstraint,
    ExistenceConstraint,
    UniquenessConstraint
]


# ============== Constraint Spec (Collection) ==============

class ConstraintSpec(BaseModel):
    """
    Complete constraint specification in DSL form.
    
    This is what the LLM generates - much simpler than LTL.
    The LTLCompiler will convert this to formal LTL.
    """
    constraints: List[DSLConstraint] = Field(default_factory=list)
    scope_table: str
    scope_description: Optional[str] = None
    
    # Metadata
    raw_query: Optional[str] = None
    confidence: float = 1.0
    
    class Config:
        extra = "ignore"  # Ignore unexpected fields from LLM output
        json_schema_extra = {
            "example": {
                "constraints": [
                    {
                        "type": "temporal",
                        "constraint_type": "quarter",
                        "quarter": "Q3",
                        "year": 2024,
                        "column": "order_date"
                    },
                    {
                        "type": "filter",
                        "field": "status",
                        "operator": "neq",
                        "value": "cancelled",
                        "is_implicit": True
                    },
                    {
                        "type": "aggregate",
                        "function": "sum",
                        "column": "amount",
                        "alias": "total_sales"
                    }
                ],
                "scope_table": "orders",
                "scope_description": "All valid orders in Q3 2024"
            }
        }


# ============== DSL to LTL Mapping ==============

# This mapping is used by the LTL compiler
OPERATOR_TO_LTL = {
    "eq": "==",
    "neq": "!=",
    "gt": ">",
    "lt": "<",
    "gte": ">=",
    "lte": "<=",
    "in": "∈",
    "not_in": "∉",
}

QUARTER_DATE_RANGES = {
    "Q1": ("01-01", "03-31"),
    "Q2": ("04-01", "06-30"),
    "Q3": ("07-01", "09-30"),
    "Q4": ("10-01", "12-31"),
}
