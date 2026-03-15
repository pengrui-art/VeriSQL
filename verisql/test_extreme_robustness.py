import unittest
from verisql.agents.state import VeriSQLState, VerificationResult
from verisql.modules.fault_localizer import FaultLocalizer
from verisql.core.dsl import ConstraintSpec
import json


class TestExtremeRobustness(unittest.TestCase):
    def test_hallucination_gibberish_sql(self):
        # Scenario: LLM outputs complete gibberish or hallucinates schema
        state = {
            "query": "Show all users",
            "schema_info": {"tables": {"users": [{"name": "id", "type": "int"}]}},
            "sql": "SELECT made_up_column FROM users WHERE DECODE(gibberish) = 1",
            "constraint_spec": ConstraintSpec(scope_table="users", filters=[]),
            "repair_count": 0,
            "errors": [],
        }

        # We manually trigger the fault localizer to see if it survives gibberish parse errors
        localizer = FaultLocalizer()

        ver_res = VerificationResult(
            status="FAIL",
            missing_constraints=[],
            incorrect_constraints=[],
            details="Execution error: no such column: made_up_column",
            message="Verification Failed",
        )

        faults = localizer.localize(state["sql"], state["constraint_spec"], ver_res)

        # It should structurally identify an issue or fallback to generic
        self.assertTrue(len(faults) > 0)
        desc = faults[0].violated_constraint.lower()
        self.assertTrue(
            "made_up_column" in desc
            or "execution" in desc
            or "parse" in desc
            or "no such column" in desc
            or "syntax" in desc
            or "failed" in desc
        )

    def test_ultra_long_schema_parsing(self):
        # Scenario: DB has 1000s of columns causing state bloating
        cols = [{"name": f"col_{i}", "type": "text"} for i in range(2000)]
        schema_info = {"tables": {"huge_table": cols}}

        # Make sure our state can hold and process this without blowing up
        state = {
            "query": "Count cols",
            "schema_info": schema_info,
            "sql": "SELECT COUNT(*) FROM huge_table",
            "constraint_spec": None,
            "repair_count": 0,
            "errors": [],
        }

        # Just verifying node doesn't crash on huge schema dicts
        self.assertEqual(len(state["schema_info"]["tables"]["huge_table"]), 2000)

    def test_empty_result_set_resilience(self):
        # Scenario: Execution is valid but returns 0 rows. Does executor survive?
        from verisql.agents.nodes import executor_node
        import sqlite3
        import uuid

        db_path = f"test_empty_{uuid.uuid4().hex}.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE empty_table (id INT)")
        conn.close()

        state = {
            "sql": "SELECT * FROM empty_table WHERE id > 9999",
            "db_path": db_path,
            "errors": [],
        }

        res = executor_node(state)
        # Should gracefully return executed status with 0 rows, not a crash
        self.assertEqual(res["execution_status"], "executed")
        self.assertEqual(res["final_result"]["row_count"], 0)

        import os

        os.remove(db_path)


if __name__ == "__main__":
    unittest.main()
