import unittest

from verisql.analyze_repair_quality import compare_repair_runs


class TestRepairQuality(unittest.TestCase):
    def test_repair_quality_summary(self):
        agent_data = {
            1: {
                "question_id": 1,
                "db_id": "sample_store",
                "question": "Q1",
                "pred_sql": "SELECT fixed",
                "ex": 1,
                "verisql": {
                    "repair_iterations": 1,
                    "repair_history": [
                        {
                            "fault_localizations": [
                                {
                                    "patch_actions": [
                                        {"action_type": "ADD_PREDICATE"},
                                        {"action_type": "FIX_BOUNDARY"},
                                    ]
                                }
                            ]
                        }
                    ],
                },
            },
            2: {
                "question_id": 2,
                "db_id": "sample_store",
                "question": "Q2",
                "pred_sql": "SELECT broken",
                "ex": 0,
                "verisql": {
                    "repair_iterations": 1,
                    "repair_history": [
                        {
                            "fault_localizations": [
                                {
                                    "patch_actions": [
                                        {"action_type": "ADD_PREDICATE"}
                                    ]
                                }
                            ]
                        }
                    ],
                },
            },
        }
        norepair_data = {
            1: {"question_id": 1, "pred_sql": "SELECT old", "ex": 0},
            2: {"question_id": 2, "pred_sql": "SELECT old", "ex": 1},
        }

        analysis = compare_repair_runs(agent_data, norepair_data)
        self.assertEqual(analysis["beneficial_repairs"], 1)
        self.assertEqual(analysis["destructive_repairs"], 1)
        self.assertIn("ADD_PREDICATE", analysis["patch_action_stats"])
        add_predicate = analysis["patch_action_stats"]["ADD_PREDICATE"]
        self.assertEqual(add_predicate["question_count"], 2)
        self.assertEqual(add_predicate["beneficial"], 1)
        self.assertEqual(add_predicate["destructive"], 1)


if __name__ == "__main__":
    unittest.main()
