"""
VeriSQL State Definition for LangGraph

Defines the state that flows through the VeriSQL workflow,
including structured repair models (PatchAction, FaultLocalization)
for counterexample-guided SQL repair.
"""

from typing import TypedDict, Optional, List, Literal, Dict
from pydantic import BaseModel, Field
from enum import Enum

from verisql.core.ilr import ILR
from verisql.core.dsl import ConstraintSpec


# ============== Verification Result ==============


class VerificationResult(BaseModel):
    """Result from the symbolic/dynamic verifier"""

    status: Literal["PASS", "FAIL", "ERROR", "SKIP"]
    message: str
    counterexample: Optional[dict] = None
    missing_constraints: List[str] = []

    # Detailed steps for UI
    verification_details: Dict[str, str] = (
        {}
    )  # e.g. {"Static": "PASS", "Dynamic": "FAIL"}


# ============== Structured Repair Models (C3: ASE Innovation) ==============


class PatchActionType(str, Enum):
    """
    Types of structured patch actions for SQL repair.

    Each type maps to a specific fault pattern that the FaultLocalizer
    can automatically diagnose from verification counterexamples.
    """

    ADD_PREDICATE = "ADD_PREDICATE"  # WHERE clause missing a required constraint
    FIX_BOUNDARY = "FIX_BOUNDARY"  # Boundary value error (> vs >=, off-by-one)
    FIX_COLUMN = "FIX_COLUMN"  # Wrong column reference
    ADD_CAST = "ADD_CAST"  # Missing type cast (e.g., integer division)
    FIX_AGGREGATION = "FIX_AGGREGATION"  # Aggregation logic error (LIMIT 1 vs subquery)
    FIX_JOIN = "FIX_JOIN"  # JOIN condition error or missing JOIN
    REPLACE_SUBQUERY = (
        "REPLACE_SUBQUERY"  # Strategy replacement (LIMIT → subquery for ties)
    )


class PatchAction(BaseModel):
    """
    A structured, clause-level repair instruction.

    Unlike free-text feedback ("fix the date filter"), a PatchAction
    specifies exactly WHICH clause to modify, the current fragment,
    and the suggested replacement — enabling deterministic repair.
    """

    action_type: PatchActionType
    target_clause: str = Field(
        ...,
        description="SQL clause location: WHERE, SELECT, JOIN, GROUP_BY, ORDER_BY, HAVING",
    )
    current_fragment: str = Field(
        default="",
        description="The current SQL fragment that needs fixing (empty if missing)",
    )
    suggested_fragment: str = Field(
        ..., description="The suggested replacement or addition"
    )
    reason: str = Field(
        ..., description="Concrete reason derived from counterexample/violation"
    )
    confidence: float = 0.8


class FaultLocalization(BaseModel):
    """
    Links a verification failure to a specific SQL fault location.

    This is the key output of the FaultLocalizer module:
    counterexample → violated constraint → SQL clause → patch action.
    """

    violated_constraint: str = Field(
        ..., description="Description of the Spec constraint that was violated"
    )
    counterexample: Optional[dict] = Field(
        default=None,
        description="The Z3/dynamic counterexample that triggered the fault",
    )
    sql_clause: str = Field(
        ..., description="The SQL clause where the fault is located (WHERE, JOIN, etc.)"
    )
    fault_type: Literal["MISSING", "INCORRECT", "BOUNDARY"] = Field(
        ...,
        description="MISSING=constraint absent, INCORRECT=wrong value, BOUNDARY=off-by-one",
    )
    patch_actions: List[PatchAction] = Field(
        default_factory=list, description="Ordered list of suggested patch actions"
    )


class RepairSuggestion(BaseModel):
    """Structured repair suggestion (legacy compatibility + new fields)"""

    issue_type: str
    description: str
    suggested_fix: str
    confidence: float = 0.8
    # New: structured fault info
    fault_localizations: List[FaultLocalization] = Field(default_factory=list)


# ============== Workflow State ==============


class VeriSQLState(TypedDict):
    """
    State that flows through the VeriSQL LangGraph workflow.

    Each node reads relevant fields and writes its outputs.
    """

    # Input
    query: str  # Original natural language query
    schema_info: Optional[dict]  # Database schema information
    db_path: Optional[str]  # Path to SQLite database for execution

    # Module outputs
    ilr: Optional[ILR]  # From AutoFormalizer
    sql: Optional[str]  # From SQL Generator
    constraint_spec: Optional[ConstraintSpec]  # From Spec Generator
    ltl_formula: Optional[str]  # From LTL Compiler

    # Verification
    verification_result: Optional[VerificationResult]

    # Structured Repair (C3)
    fault_localizations: List[FaultLocalization]  # From FaultLocalizer
    patch_actions: List[PatchAction]  # Flattened action list for SQL generator

    # Repair loop
    repair_count: int
    repair_history: List[RepairSuggestion]
    current_feedback: Optional[str]

    # Final output
    final_sql: Optional[str]
    final_result: Optional[dict]
    execution_status: Literal["pending", "verified", "executed", "failed"]

    # Metadata
    errors: List[str]

    # Ablation Study Configurations (C2.2)
    ablation_mode: Optional[str]  # "none", "no_dynamic", "no_repair"
