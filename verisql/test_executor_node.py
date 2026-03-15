import unittest
import sqlite3
import time
from pathlib import Path

from verisql.agents.nodes import executor_node
from verisql.agents.state import VerificationResult


class TestExecutorNode(unittest.TestCase):
    def setUp(self):
        # Create a small temp DB for tests
        import uuid

        self.db_path = f"test_exec_{uuid.uuid4().hex}.sqlite"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE sample (id INT, val TEXT)")
        for i in range(10):
            cursor.execute("INSERT INTO sample VALUES (?, ?)", (i, f"val_{i}"))
        conn.commit()
        conn.close()

    def tearDown(self):
        if Path(self.db_path).exists():
            Path(self.db_path).unlink()

    def test_executor_normal_execution(self):
        state = {"sql": "SELECT * FROM sample LIMIT 5", "db_path": self.db_path}
        res = executor_node(state)
        self.assertEqual(res["execution_status"], "executed")
        self.assertEqual(len(res["final_result"]["rows"]), 5)

    def test_executor_syntax_error(self):
        state = {"sql": "SELECT * FROM doesnt_exist", "db_path": self.db_path}
        res = executor_node(state)
        self.assertEqual(res["execution_status"], "failed")
        self.assertTrue("no such table" in str(res["errors"][0]))

    def test_executor_memory_overflow_protection(self):
        # Memory timeout check using cross join
        # 10^4 = 10000 rows
        mem_sql = "SELECT * FROM sample a, sample b, sample c, sample d"
        state_mem = {"sql": mem_sql, "db_path": self.db_path}
        res_mem = executor_node(state_mem)

        self.assertEqual(res_mem["execution_status"], "executed")
        # Only up to 100 presented to the LLM context
        self.assertLessEqual(len(res_mem["final_result"]["rows"]), 100)
        # Verify the row_count reports up to the fetchmany limit (1001) preventing OOM
        self.assertEqual(res_mem["final_result"]["row_count"], 1001)

    def test_executor_blocks_unverified_sql(self):
        state = {
            "sql": "SELECT * FROM sample",
            "db_path": self.db_path,
            "verification_result": VerificationResult(
                status="FAIL", message="verification failed"
            ),
            "errors": [],
        }
        res = executor_node(state)
        self.assertEqual(res["execution_status"], "failed")
        self.assertFalse(res["final_result"]["verified"])
        self.assertIn("blocked", res["final_result"]["error"].lower())

    def test_executor_blocks_mutating_sql(self):
        state = {"sql": "DELETE FROM sample", "db_path": self.db_path, "errors": []}
        res = executor_node(state)
        self.assertEqual(res["execution_status"], "failed")
        self.assertFalse(res["final_result"]["verified"])
        self.assertIn("read-only", res["final_result"]["error"].lower())


if __name__ == "__main__":
    unittest.main()
