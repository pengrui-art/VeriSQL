"""
Test spec_utils.py - Spec sanitization and safe parsing

Run with: python verisql/test_spec_utils.py
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.getcwd()))

from verisql.utils.spec_utils import (
    sanitize_constraint,
    sanitize_spec_json,
    parse_spec_safely,
    validate_spec,
)
from verisql.core.dsl import ConstraintSpec, FilterDSL


def test_sanitize_filter():
    """Test filter constraint sanitization"""
    print("Test 1: Sanitize filter with wrong operator...")
    
    raw = {
        "type": "Filter",  # Wrong case
        "field": "status",
        "operator": "!=",  # Wrong format
        "value": "cancelled"
    }
    
    result = sanitize_constraint(raw)
    assert result is not None, "Should not return None"
    assert result["type"] == "filter", f"Type should be 'filter', got {result['type']}"
    assert result["operator"] == "neq", f"Operator should be 'neq', got {result['operator']}"
    print("✅ Filter sanitization works!")


def test_sanitize_temporal():
    """Test temporal constraint sanitization"""
    print("\nTest 2: Sanitize temporal with missing constraint_type...")
    
    raw = {
        "type": "temporal",
        "quarter": "3",  # Missing Q prefix
        "year": "2024",  # String instead of int
        "column": "order_date"
    }
    
    result = sanitize_constraint(raw)
    assert result is not None, "Should not return None"
    assert result["constraint_type"] == "quarter", f"Should infer 'quarter', got {result.get('constraint_type')}"
    assert result["quarter"] == "Q3", f"Should normalize to 'Q3', got {result.get('quarter')}"
    assert result["year"] == 2024, f"Year should be int, got {type(result.get('year'))}"
    print("✅ Temporal sanitization works!")


def test_sanitize_aggregate():
    """Test aggregate constraint sanitization"""
    print("\nTest 3: Sanitize aggregate with wrong function name...")
    
    raw = {
        "type": "aggregate",
        "function": "maximum",  # Wrong name
        "column": "amount"
    }
    
    result = sanitize_constraint(raw)
    assert result is not None, "Should not return None"
    assert result["function"] == "max", f"Should normalize to 'max', got {result.get('function')}"
    print("✅ Aggregate sanitization works!")


def test_sanitize_spec():
    """Test full spec sanitization"""
    print("\nTest 4: Sanitize complete spec with mixed issues...")
    
    raw_spec = {
        "table": "orders",  # Should be "scope_table"
        "constraints": [
            {"type": "filter", "field": "status", "operator": "==", "value": "active"},
            {"type": "TEMPORAL", "constraint_type": "Q", "quarter": "Q1", "column": "date"},
            {"type": "invalid_type", "foo": "bar"},  # Should be skipped
        ]
    }
    
    result = sanitize_spec_json(raw_spec)
    assert result["scope_table"] == "orders", f"Should extract from 'table', got {result.get('scope_table')}"
    assert len(result["constraints"]) == 2, f"Should have 2 valid constraints, got {len(result['constraints'])}"
    print("✅ Full spec sanitization works!")


def test_parse_safely():
    """Test safe parsing of LLM output"""
    print("\nTest 5: Parse spec safely from malformed LLM output...")
    
    llm_output = '''
    Here is the constraint spec:
    ```json
    {
      "scope_table": "orders",
      "constraints": [
        {"type": "filter", "field": "status", "operator": "neq", "value": "cancelled"}
      ]
    }
    ```
    '''
    
    spec = parse_spec_safely(llm_output)
    assert isinstance(spec, ConstraintSpec), "Should return ConstraintSpec"
    assert spec.scope_table == "orders", f"scope_table should be 'orders', got {spec.scope_table}"
    assert len(spec.constraints) == 1, f"Should have 1 constraint, got {len(spec.constraints)}"
    print("✅ Safe parsing works!")


def test_parse_safely_fallback():
    """Test that parse_spec_safely returns valid spec even on failure"""
    print("\nTest 6: Parse spec safely with completely invalid input...")
    
    bad_output = "This is not JSON at all!"
    
    spec = parse_spec_safely(bad_output, fallback_table="default_table")
    assert isinstance(spec, ConstraintSpec), "Should return ConstraintSpec even on error"
    assert spec.scope_table == "default_table", f"Should use fallback table"
    assert len(spec.constraints) == 0, "Should have empty constraints"
    print("✅ Fallback behavior works!")


def test_validate_spec():
    """Test spec validation"""
    print("\nTest 7: Validate spec and get issues...")
    
    # Empty spec
    empty_spec = ConstraintSpec(scope_table="", constraints=[])
    issues = validate_spec(empty_spec)
    assert len(issues) >= 2, f"Should have at least 2 issues, got {len(issues)}"
    print(f"  Issues found: {issues}")
    
    # Valid spec
    valid_spec = ConstraintSpec(
        scope_table="orders",
        constraints=[FilterDSL(field="status", operator="eq", value="active")]
    )
    issues = validate_spec(valid_spec)
    assert len(issues) == 0, f"Should have no issues, got {issues}"
    print("✅ Validation works!")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing spec_utils.py")
    print("=" * 60)
    
    try:
        test_sanitize_filter()
        test_sanitize_temporal()
        test_sanitize_aggregate()
        test_sanitize_spec()
        test_parse_safely()
        test_parse_safely_fallback()
        test_validate_spec()
        
        print("\n" + "=" * 60)
        print("All tests passed! ✅")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
