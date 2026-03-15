import unittest
from pathlib import Path

from verisql.run_metadata import (
    build_dataset_slice_label,
    build_run_name,
    finalize_run_metadata,
)


class TestRunMetadata(unittest.TestCase):
    def test_dataset_slice_label(self):
        label = build_dataset_slice_label(
            Path("verisql/DataBase/Bird/dev_20240627/dev_tied_append.json"),
            "financial",
            100,
            5,
        )
        self.assertEqual(label, "dev_tied_append_db-financial_l100_o5")

    def test_finalize_run_metadata(self):
        metadata = {
            "run_id": "demo",
            "run_name": "demo",
            "created_at": "2026-03-15T00:00:00+08:00",
        }
        finalized = finalize_run_metadata(
            metadata,
            completed_questions=3,
            metrics={"ex_rate": 1.0},
        )
        self.assertEqual(finalized["completed_questions"], 3)
        self.assertEqual(finalized["metrics"]["ex_rate"], 1.0)
        self.assertIn("completed_at", finalized)

    def test_build_run_name_contains_key_dimensions(self):
        run_name = build_run_name(
            study="bird",
            pred_source="agent",
            ablation_mode="none",
            data_path=Path("dev_tied_append.json"),
            db_id=None,
            limit=10,
            offset=0,
        )
        self.assertIn("bird_agent", run_name)
        self.assertIn("abl-none", run_name)
        self.assertIn("db-all", run_name)


if __name__ == "__main__":
    unittest.main()
