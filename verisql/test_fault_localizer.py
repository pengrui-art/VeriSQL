"""
Test FaultLocalizer Module

Tests for C3: Counterexample-Guided Structured Repair.
Validates that the FaultLocalizer correctly:
1. Identifies MISSING constraints → ADD_PREDICATE
2. Identifies BOUNDARY errors → FIX_BOUNDARY
3. Returns empty faults for correct SQL
4. Handles temporal constraint localization
5. Formats patch actions into structured text
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verisql.modules.fault_localizer import FaultLocalizer, format_patch_actions
from verisql.agents.state import VerificationResult, PatchActionType
from verisql.core.dsl import ConstraintSpec, FilterDSL, TemporalConstraint, AggregateConstraint


def test_missing_filter_generates_add_predicate():
    """
    Case 1: SQL is missing a WHERE filter that the Spec requires.
    FaultLocalizer should detect MISSING fault and suggest ADD_PREDICATE.
    """
    print("Test 1: Missing filter → ADD_PREDICATE")
    
    spec = ConstraintSpec(
        scope_table="orders",
        constraints=[
            FilterDSL(field="status", operator="neq", value="cancelled")
        ],
    )
    
    # SQL does NOT filter by status
    sql = "SELECT * FROM orders WHERE amount > 100"
    
    result = VerificationResult(
        status="FAIL",
        message="Symbolic Verification FAILED",
        counterexample={"status": "cancelled", "amount": "150"},
        missing_constraints=["status != cancelled"],
    )
    
    localizer = FaultLocalizer()
    faults = localizer.localize(sql, spec, result)
    
    assert len(faults) == 1, f"Expected 1 fault, got {len(faults)}"
    fault = faults[0]
    
    assert fault.fault_type == "MISSING", f"Expected MISSING, got {fault.fault_type}"
    assert fault.sql_clause == "WHERE", f"Expected WHERE clause, got {fault.sql_clause}"
    assert len(fault.patch_actions) == 1, f"Expected 1 patch action, got {len(fault.patch_actions)}"
    
    action = fault.patch_actions[0]
    assert action.action_type == PatchActionType.ADD_PREDICATE
    assert "status" in action.suggested_fragment
    assert "cancelled" in action.suggested_fragment
    
    print(f"  ✅ Fault type: {fault.fault_type}")
    print(f"  ✅ Action: {action.action_type.value}")
    print(f"  ✅ Suggestion: {action.suggested_fragment}")
    print(f"  ✅ Reason: {action.reason}")


def test_boundary_error_generates_fix_boundary():
    """
    Case 2: SQL has a date filter but with wrong boundary values.
    FaultLocalizer should detect BOUNDARY fault and suggest FIX_BOUNDARY.
    """
    print("\nTest 2: Boundary error → FIX_BOUNDARY")
    
    spec = ConstraintSpec(
        scope_table="orders",
        constraints=[
            TemporalConstraint(
                constraint_type="quarter",
                quarter="Q3",
                year=2024,
                column="order_date",
            )
        ],
    )
    
    # SQL has wrong date boundary (July 2 instead of July 1)
    sql = "SELECT * FROM orders WHERE order_date BETWEEN '2024-07-02' AND '2024-09-30'"
    
    result = VerificationResult(
        status="FAIL",
        message="Boundary violation",
        counterexample={"order_date_as_int": "20240701"},
    )
    
    localizer = FaultLocalizer()
    faults = localizer.localize(sql, spec, result)
    
    assert len(faults) == 1, f"Expected 1 fault, got {len(faults)}"
    fault = faults[0]
    
    assert fault.fault_type == "BOUNDARY", f"Expected BOUNDARY, got {fault.fault_type}"
    assert len(fault.patch_actions) >= 1
    
    action = fault.patch_actions[0]
    assert action.action_type == PatchActionType.FIX_BOUNDARY
    assert "2024-07-01" in action.suggested_fragment
    
    print(f"  ✅ Fault type: {fault.fault_type}")
    print(f"  ✅ Action: {action.action_type.value}")
    print(f"  ✅ Current: {action.current_fragment}")
    print(f"  ✅ Suggested: {action.suggested_fragment}")


def test_correct_sql_returns_no_faults():
    """
    Case 3: SQL correctly implements all Spec constraints.
    FaultLocalizer should return empty fault list.
    """
    print("\nTest 3: Correct SQL → no faults")
    
    spec = ConstraintSpec(
        scope_table="orders",
        constraints=[
            FilterDSL(field="status", operator="neq", value="cancelled"),
        ],
    )
    
    sql = "SELECT * FROM orders WHERE status != 'cancelled'"
    
    result = VerificationResult(
        status="PASS",
        message="Verification passed",
    )
    
    localizer = FaultLocalizer()
    faults = localizer.localize(sql, spec, result)
    
    assert len(faults) == 0, f"Expected 0 faults, got {len(faults)}"
    print("  ✅ No faults generated for correct SQL")


def test_missing_temporal_generates_add_predicate():
    """
    Case 4: SQL is missing any temporal filter.
    FaultLocalizer should suggest adding the full BETWEEN clause.
    """
    print("\nTest 4: Missing temporal → ADD_PREDICATE with BETWEEN")
    
    spec = ConstraintSpec(
        scope_table="orders",
        constraints=[
            TemporalConstraint(
                constraint_type="quarter",
                quarter="Q3",
                year=2024,
                column="order_date",
            )
        ],
    )
    
    # SQL has NO date filter
    sql = "SELECT * FROM orders WHERE amount > 50"
    
    result = VerificationResult(
        status="FAIL",
        message="Missing temporal constraint",
        counterexample={"order_date_as_int": "20240101"},
    )
    
    localizer = FaultLocalizer()
    faults = localizer.localize(sql, spec, result)
    
    assert len(faults) == 1, f"Expected 1 fault, got {len(faults)}"
    fault = faults[0]
    
    assert fault.fault_type == "MISSING"
    action = fault.patch_actions[0]
    assert action.action_type == PatchActionType.ADD_PREDICATE
    assert "BETWEEN" in action.suggested_fragment
    assert "2024-07-01" in action.suggested_fragment
    assert "2024-09-30" in action.suggested_fragment
    
    print(f"  ✅ Suggestion: {action.suggested_fragment}")


def test_missing_aggregate_generates_fix_aggregation():
    """
    Case 5: Spec requires MAX() but SQL doesn't use it.
    """
    print("\nTest 5: Missing aggregate → FIX_AGGREGATION")
    
    spec = ConstraintSpec(
        scope_table="orders",
        constraints=[
            AggregateConstraint(function="max", column="amount", alias="highest"),
        ],
    )
    
    sql = "SELECT amount FROM orders ORDER BY amount DESC LIMIT 1"
    
    result = VerificationResult(
        status="FAIL",
        message="Missing aggregate",
    )
    
    localizer = FaultLocalizer()
    faults = localizer.localize(sql, spec, result)
    
    assert len(faults) >= 1
    found_agg = any(
        a.action_type == PatchActionType.FIX_AGGREGATION
        for f in faults for a in f.patch_actions
    )
    assert found_agg, "Should generate FIX_AGGREGATION action"
    print("  ✅ FIX_AGGREGATION action generated")


def test_format_patch_actions():
    """
    Case 6: format_patch_actions generates readable structured text.
    """
    print("\nTest 6: format_patch_actions formatting")
    
    from verisql.agents.state import FaultLocalization, PatchAction, PatchActionType
    
    faults = [
        FaultLocalization(
            violated_constraint="status != cancelled",
            sql_clause="WHERE",
            fault_type="MISSING",
            patch_actions=[
                PatchAction(
                    action_type=PatchActionType.ADD_PREDICATE,
                    target_clause="WHERE",
                    suggested_fragment="status != 'cancelled'",
                    reason="No filter on status column",
                    confidence=0.9,
                )
            ],
        )
    ]
    
    text = format_patch_actions(faults)
    
    assert "[PATCH-1]" in text, "Should contain patch numbering"
    assert "ADD_PREDICATE" in text, "Should contain action type"
    assert "WHERE" in text, "Should contain clause location"
    assert "status" in text, "Should contain the fix"
    
    print(f"  ✅ Formatted output:\n{text}")


def test_multiple_faults():
    """
    Case 7: Multiple spec violations should generate multiple faults.
    """
    print("\nTest 7: Multiple violations → multiple faults")
    
    spec = ConstraintSpec(
        scope_table="orders",
        constraints=[
            FilterDSL(field="status", operator="neq", value="cancelled"),
            TemporalConstraint(
                constraint_type="quarter", quarter="Q3", year=2024, column="order_date"
            ),
        ],
    )
    
    # SQL missing BOTH constraints
    sql = "SELECT * FROM orders WHERE amount > 100"
    
    result = VerificationResult(
        status="FAIL",
        message="Multiple constraints missing",
        counterexample={"status": "cancelled", "order_date_as_int": "20240101"},
    )
    
    localizer = FaultLocalizer()
    faults = localizer.localize(sql, spec, result)
    
    assert len(faults) == 2, f"Expected 2 faults, got {len(faults)}"
    
    # Verify both are MISSING type
    types = [f.fault_type for f in faults]
    assert all(t == "MISSING" for t in types), f"All should be MISSING, got {types}"
    
    # Format should have two patches
    text = format_patch_actions(faults)
    assert "[PATCH-1]" in text
    assert "[PATCH-2]" in text
    
    print(f"  ✅ Generated {len(faults)} faults with {sum(len(f.patch_actions) for f in faults)} patch actions")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing FaultLocalizer (C3: Structured Repair)")
    print("=" * 60)
    
    try:
        test_missing_filter_generates_add_predicate()
        test_boundary_error_generates_fix_boundary()
        test_correct_sql_returns_no_faults()
        test_missing_temporal_generates_add_predicate()
        test_missing_aggregate_generates_fix_aggregation()
        test_format_patch_actions()
        test_multiple_faults()
        
        print("\n" + "=" * 60)
        print("All 7 tests passed! ✅")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
