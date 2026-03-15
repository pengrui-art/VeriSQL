import unittest

from verisql.utils.llm_usage import (
    empty_usage_summary,
    make_usage_event,
    merge_usage_summaries,
)


class FakeResponse:
    def __init__(self, usage_metadata=None, response_metadata=None):
        self.usage_metadata = usage_metadata or {}
        self.response_metadata = response_metadata or {}


class TestLLMUsage(unittest.TestCase):
    def test_usage_metadata_extraction(self):
        response = FakeResponse(
            usage_metadata={"input_tokens": 100, "output_tokens": 25, "total_tokens": 125}
        )
        event = make_usage_event(
            response,
            stage="intent_parser",
            model="gpt-4o",
            provider="openai",
        )
        self.assertEqual(event["prompt_tokens"], 100)
        self.assertEqual(event["completion_tokens"], 25)
        self.assertEqual(event["total_tokens"], 125)
        self.assertIsNotNone(event["estimated_cost_usd"])

    def test_usage_summary_merging(self):
        summary = empty_usage_summary()
        first = make_usage_event(
            FakeResponse(usage_metadata={"input_tokens": 10, "output_tokens": 5}),
            stage="a",
            model="gpt-4o",
            provider="openai",
        )
        second = make_usage_event(
            FakeResponse(response_metadata={"token_usage": {"prompt_tokens": 8, "completion_tokens": 2}}),
            stage="b",
            model="gpt-4o",
            provider="openai",
        )
        summary = merge_usage_summaries(summary, first)
        summary = merge_usage_summaries(summary, second)
        totals = summary["totals"]
        self.assertEqual(totals["call_count"], 2)
        self.assertEqual(totals["prompt_tokens"], 18)
        self.assertEqual(totals["completion_tokens"], 7)
        self.assertEqual(totals["total_tokens"], 25)


if __name__ == "__main__":
    unittest.main()
