
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.getcwd()))

from verisql.core.dsl import ConstraintSpec, FilterDSL
from verisql.utils.z3_utils import verify_sql_against_spec

def test_z3_verification():
    print("Testing Z3 Symbolic Verification...")
    
    # Define a spec: status != 'cancelled'
    spec = ConstraintSpec(
        scope_table="orders",
        constraints=[
            FilterDSL(field="status", operator="neq", value="cancelled")
        ],
        raw_query="non-cancelled orders"
    )
    
    # Case 1: PASS
    # SQL includes the constraint
    sql_pass = "SELECT * FROM orders WHERE status != 'cancelled'"
    result_pass = verify_sql_against_spec(sql_pass, spec)
    print(f"\n[Case 1] Expected PASS. Result: {result_pass.status}")
    if result_pass.status == "PASS":
        print("✅ Success")
    else:
        print(f"❌ Failed: {result_pass.message}")

    # Case 2: FAIL
    # SQL misses the constraint
    sql_fail = "SELECT * FROM orders WHERE amount > 100"
    result_fail = verify_sql_against_spec(sql_fail, spec)
    print(f"\n[Case 2] Expected FAIL. Result: {result_fail.status}")
    
    if result_fail.status == "FAIL":
        print("✅ Success (Correctly caught missing constraint)")
        print(f"Counterexample: {result_fail.counterexample}")
    else:
        print(f"❌ Failed to catch error. Status: {result_fail.status}")

if __name__ == "__main__":
    test_z3_verification()
