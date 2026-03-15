import unittest
import shutil
from pathlib import Path
from verisql.eval_utils import CheckpointManager, MetricsCalculator

class TestEvalScripts(unittest.TestCase):
    def test_checkpoint_manager(self):
        tmp_root = Path(__file__).resolve().parents[1] / "paper_data" / "tmp_tests"
        test_dir = tmp_root / "checkpoint_manager"
        jsonl_path = test_dir / 'test_results.jsonl'
        try:
            shutil.rmtree(test_dir, ignore_errors=True)
            manager = CheckpointManager(str(jsonl_path))

            # initially empty
            completed = manager.load_completed()
            self.assertEqual(len(completed), 0)

            # write some records
            manager.append_result({'question_id': 1, 'ex': 1})
            manager.append_result({'question_id': 2, 'ex': 0})
            manager.append_result({'error': 'some runtime error'}) # record without question_id

            # reload
            manager2 = CheckpointManager(str(jsonl_path))
            completed2 = manager2.load_completed()
            self.assertEqual(len(completed2), 2)
            self.assertIn(1, completed2)
            self.assertIn(2, completed2)
            self.assertNotIn(3, completed2)
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    def test_metrics_calculator(self):
        mock_results = [
            # Case 1: Perfect: ex=1, verified=True
            {'question_id': 1, 'ex': 1, 'pred_exec_ok': True, 'verisql': {'verified': True}, 'latency': 1.5},
            # Case 2: SVR penalty: executed OK but verified=False
            {'question_id': 2, 'ex': 0, 'pred_exec_ok': True, 'verisql': {'verified': False}, 'latency': 2.0},
            # Case 3: Syntax error, not verified
            {'question_id': 3, 'ex': 0, 'pred_exec_ok': False, 'verisql': {'verified': False}, 'latency': 1.0},
            # Case 4: EX=1 but constraint bypassed/unverified
            {'question_id': 4, 'ex': 1, 'pred_exec_ok': True, 'verisql': {'verified': False}, 'latency': 3.5}
        ]
        
        metrics = MetricsCalculator.compute(mock_results)
        
        self.assertEqual(metrics['total'], 4)
        self.assertEqual(metrics['ex_rate'], 0.5)
        self.assertEqual(metrics['svr'], 0.5)
        self.assertEqual(metrics['caa'], 0.25)
        self.assertEqual(metrics['avg_latency'], 2.0)

if __name__ == '__main__':
    unittest.main()
