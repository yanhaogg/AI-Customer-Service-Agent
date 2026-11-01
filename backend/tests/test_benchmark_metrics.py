"""确保评测指标的分母、未找到结果口径与延迟分位数计算明确。"""

import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts/benchmark_agent.py"
spec = importlib.util.spec_from_file_location("benchmark_agent", path)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkMetricsTests(unittest.TestCase):
    def test_rates_include_failures_and_separate_expected_not_found(self):
        records = [
            dict(
                metadata={"tools": [{"status": "ok"}, {"status": "not_found"}]},
                elapsed_seconds=2,
                answer_pass=True,
                tool_requirement_pass=True,
                message_status="completed",
            ),
            dict(
                metadata={"tools": [{"status": "ok"}, {"status": "unavailable"}]},
                elapsed_seconds=10,
                answer_pass=False,
                tool_requirement_pass=False,
                message_status="failed",
            ),
        ]
        result = benchmark.summarize(records)
        self.assertEqual(result["answer_pass_rate"], 0.5)
        self.assertEqual(result["response_completion_rate"], 0.5)
        self.assertEqual(result["tool_execution_success_rate"], 0.75)
        self.assertEqual(result["tool_ok_only_rate"], 0.5)
        self.assertEqual(result["latency_seconds"]["mean"], 6)
        self.assertAlmostEqual(result["latency_seconds"]["p95"], 9.6)


if __name__ == "__main__":
    unittest.main()
