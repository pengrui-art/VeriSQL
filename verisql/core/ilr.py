"""
ILR (Intent Logic Representation) Schema

Core intermediate representation that bridges NL understanding and SQL/Spec generation.
This is the key innovation of VeriSQL - providing a common reference point
that reduces correlated hallucination risk.
"""
from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field
from enum import Enum


class OperationType(str, Enum):
    """Supported SQL operation types"""
    SELECT = "SELECT"
    AGGREGATE = "AGGREGATE"
    COUNT = "COUNT"
    JOIN = "JOIN"
    SUBQUERY = "SUBQUERY"


class AggregateFunction(str, Enum):
    """Aggregate functions"""
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    MIN = "MIN"
    MAX = "MAX"


class ComparisonOperator(str, Enum):
    """Comparison operators for constraints"""
    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUALS = ">="
    LESS_EQUALS = "<="
    IN = "IN"
    NOT_IN = "NOT_IN"
    LIKE = "LIKE"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"


class ConstraintSource(str, Enum):
    """Source of the constraint - explicit from user or implicit business rule"""
    EXPLICIT = "EXPLICIT"  # User explicitly mentioned
    IMPLICIT_BUSINESS_RULE = "IMPLICIT_BUSINESS_RULE"  # Inferred from domain knowledge
    SCHEMA_CONSTRAINT = "SCHEMA_CONSTRAINT"  # From database schema


class TemporalType(str, Enum):
    """Type of temporal specification"""
    ABSOLUTE = "ABSOLUTE"  # e.g., "2024-01-01 to 2024-03-31"
    RELATIVE = "RELATIVE"  # e.g., "last 30 days"
    NAMED = "NAMED"  # e.g., "Q3", "last_year"


class TieBreakingStrategy(str, Enum):
    """Strategy for handling ties in extremes (highest/lowest)"""
    ALL_TIES = "ALL_TIES"  # Return all entities with the extreme value (Default)
    ARBITRARY_ONE = "ARBITRARY_ONE"  # explicit "limit 1", "top 1"
    NONE = "NONE"  # Not an extreme value query



# ============== Constraint Types ==============

class FilterConstraint(BaseModel):
    """Basic filter constraint"""
    type: Literal["FilterConstraint"] = "FilterConstraint"
    field: str = Field(..., description="Column name")
    op: ComparisonOperator
    value: Union[str, int, float, bool, List[str]]
    source: ConstraintSource = ConstraintSource.EXPLICIT
    description: Optional[str] = None


class ExistentialConstraint(BaseModel):
    """EXISTS/NOT EXISTS subquery constraint"""
    type: Literal["ExistentialConstraint"] = "ExistentialConstraint"
    exists: bool = True  # EXISTS vs NOT EXISTS
    subquery_entity: str
    subquery_condition: str
    source: ConstraintSource = ConstraintSource.EXPLICIT


class NegationConstraint(BaseModel):
    """Negation of another constraint"""
    type: Literal["NegationConstraint"] = "NegationConstraint"
    inner: "Constraint"
    source: ConstraintSource = ConstraintSource.EXPLICIT


class CompositeConstraint(BaseModel):
    """Combination of multiple constraints"""
    type: Literal["CompositeConstraint"] = "CompositeConstraint"
    combinator: Literal["AND", "OR"]
    constraints: List["Constraint"]
    source: ConstraintSource = ConstraintSource.EXPLICIT


Constraint = Union[FilterConstraint, ExistentialConstraint, NegationConstraint, CompositeConstraint]


# ============== Scope Definition ==============

class TemporalSpec(BaseModel):
    """Temporal specification with explicit resolution"""
    type: TemporalType
    value: str  # Original value like "Q3" or "last_year"
    resolved_start: Optional[str] = None  # Resolved to actual date: "2024-07-01"
    resolved_end: Optional[str] = None  # Resolved to actual date: "2024-09-30"
    column: Optional[str] = None  # Which column to apply this filter


class EntityRef(BaseModel):
    """Reference to a database entity (table)"""
    table: str
    db_schema: Optional[str] = Field(None, alias="database_schema")
    alias: Optional[str] = None
    
    model_config = {
        "populate_by_name": True
    }




class JoinSpec(BaseModel):
    """Join specification"""
    target_entity: EntityRef
    join_type: Literal["INNER", "LEFT", "RIGHT", "FULL"] = "INNER"
    on_condition: str


class Scope(BaseModel):
    """Query scope definition - captures what SQL often misses"""
    entity: EntityRef
    temporal: Optional[TemporalSpec] = None
    joins: List[JoinSpec] = Field(default_factory=list)


# ============== Operation Definition ==============

class AggregateOp(BaseModel):
    """Aggregate operation"""
    type: Literal["AGGREGATE"] = "AGGREGATE"
    function: AggregateFunction
    target: str  # Column to aggregate
    distinct: bool = False


class SelectOp(BaseModel):
    """Select operation"""
    type: Literal["SELECT"] = "SELECT"
    columns: List[str]
    distinct: bool = False


class CountOp(BaseModel):
    """Count operation"""
    type: Literal["COUNT"] = "COUNT"
    target: Optional[str] = None  # None means COUNT(*)
    distinct: bool = False


Operation = Union[AggregateOp, SelectOp, CountOp]


# ============== Output Specification ==============

class GroupBySpec(BaseModel):
    """GROUP BY specification"""
    columns: List[str]
    having: Optional[str] = None


class OrderBySpec(BaseModel):
    """ORDER BY specification"""
    column: str
    direction: Literal["ASC", "DESC"] = "ASC"


class OutputSpec(BaseModel):
    """Output format specification"""
    format: Literal["SCALAR", "TABLE", "LIST"] = "TABLE"
    alias: Optional[str] = None
    group_by: Optional[GroupBySpec] = None
    order_by: List[OrderBySpec] = Field(default_factory=list)
    limit: Optional[int] = None
    tie_strategy: TieBreakingStrategy = TieBreakingStrategy.NONE


# ============== Main ILR Schema ==============

class ILR(BaseModel):
    """
    Intent Logic Representation - The core intermediate representation
    
    This is more abstract than SQL and closer to natural language logic structure.
    It explicitly captures:
    1. Scope (temporal, spatial) that SQL often misses
    2. Both explicit and implicit business constraints
    3. Resolved ambiguities (e.g., Q3 -> 07-01 to 09-30)
    """
    raw_query: str = Field(..., description="Original natural language query")
    scope: Scope
    operation: Operation
    constraints: List[Constraint] = Field(default_factory=list)
    output: OutputSpec = Field(default_factory=OutputSpec)
    
    # Metadata
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    ambiguities_resolved: List[str] = Field(default_factory=list)
    implicit_constraints_added: List[str] = Field(default_factory=list)
    
    class Config:
        json_schema_extra = {
            "example": {
                "raw_query": "What is the total sales of active products in Q3?",
                "scope": {
                    "entity": {"table": "orders", "alias": "o"},
                    "temporal": {
                        "type": "NAMED",
                        "value": "Q3",
                        "resolved_start": "2024-07-01",
                        "resolved_end": "2024-09-30",
                        "column": "order_date"
                    }
                },
                "operation": {
                    "type": "AGGREGATE",
                    "function": "SUM",
                    "target": "amount"
                },
                "constraints": [
                    {
                        "type": "FilterConstraint",
                        "field": "status",
                        "op": "!=",
                        "value": "cancelled",
                        "source": "IMPLICIT_BUSINESS_RULE"
                    }
                ],
                "output": {
                    "format": "SCALAR",
                    "alias": "total_sales"
                }
            }
        }


# Update forward references for recursive types
NegationConstraint.model_rebuild()
CompositeConstraint.model_rebuild()
