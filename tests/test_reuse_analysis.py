import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "reuse_analysis", Path(__file__).resolve().parents[1] / "research/reuse_analysis.py"
)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class ReuseAnalysisTests(unittest.TestCase):
    def test_identical_prompt_timing_jitter_is_not_a_speedup(self):
        self.assertIsNone(analysis.break_even_uses(100, 5, 4.99, False))

    def test_conditional_crossover_requires_positive_marginal_savings(self):
        self.assertEqual(analysis.break_even_uses(100, 5, 3, True), 50)
        self.assertIsNone(analysis.break_even_uses(100, 5, 6, True))
        with self.assertRaises(ValueError):
            analysis.break_even_uses(100, float("nan"), 3, True)
