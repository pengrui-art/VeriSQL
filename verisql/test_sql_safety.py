import unittest

from verisql.utils.sql_safety import validate_read_only_sql


class TestSQLSafety(unittest.TestCase):
    def test_select_is_allowed(self):
        ok, error = validate_read_only_sql("SELECT * FROM sample")
        self.assertTrue(ok)
        self.assertEqual(error, "")

    def test_delete_is_blocked(self):
        ok, error = validate_read_only_sql("DELETE FROM sample")
        self.assertFalse(ok)
        self.assertIn("read-only", error.lower())

    def test_multiple_statements_are_blocked(self):
        ok, error = validate_read_only_sql("SELECT 1; SELECT 2")
        self.assertFalse(ok)
        self.assertIn("single sql statement", error.lower())


if __name__ == "__main__":
    unittest.main()
