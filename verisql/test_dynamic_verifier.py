
import sys
import os
import sys
import os
# Add parent directory to path to allow 'import verisql...'
sys.path.append(os.path.dirname(os.getcwd()))

try:
    from verisql.modules.dynamic_verifier import DynamicVerifier
    from verisql.core.dsl import ConstraintSpec, FilterDSL, TemporalConstraint

    # Mock Schema
    schema_info = {
        "tables": {
            "orders": ["order_id", "status", "order_date", "amount"]
        }
    }

    # Spec: Status != 'cancelled' AND Q3 2024
    spec = ConstraintSpec(
        scope_table="orders",
        constraints=[
            FilterDSL(field="status", operator="neq", value="cancelled"),
            TemporalConstraint(constraint_type="quarter", quarter="Q3", year=2024, column="order_date")
        ],
        raw_query="Test query" 
    )

    verifier = DynamicVerifier(schema_info)

    # Case 1: Correct SQL (filters both)
    sql_correct = "SELECT * FROM orders WHERE status != 'cancelled' AND order_date BETWEEN '2024-07-01' AND '2024-09-30'"
    print(f"Testing Correct SQL: {sql_correct}")
    res = verifier.verify(sql_correct, spec)
    print(f"Result: {res.status} - {res.message}")
    print("-" * 20)

    # Case 2: Incorrect SQL (Missing status filter)
    sql_wrong = "SELECT * FROM orders WHERE order_date BETWEEN '2024-07-01' AND '2024-09-30'"
    print(f"Testing Wrong SQL (Missing Status Filter): {sql_wrong}")
    res = verifier.verify(sql_wrong, spec)
    print(f"Result: {res.status} - {res.message}")
    if res.missing_constraints:
        print(f"Violations: {res.missing_constraints}")
    print("-" * 20)
    
except Exception as e:
    import traceback
    traceback.print_exc()
