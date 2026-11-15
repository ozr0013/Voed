"""Unit tests for the pure scoring helpers.  Run: python -m unittest evals.test_scoring"""
import unittest

from evals.scoring import aggregate, match_action, percentile, wilson


class MatchAction(unittest.TestCase):
    ALTS = [
        {"name": "cut_range", "params": {"start_s": 0, "end_s": 10}},
        {"name": "trim", "params": {"start_s": 10, "end_s": 20}},
    ]

    def test_exact(self):
        self.assertEqual(match_action({"name": "cut_range", "start_s": 0, "end_s": 10}, self.ALTS),
                         (True, True, 0))

    def test_matches_second_alternative(self):
        self.assertEqual(match_action({"name": "trim", "start_s": 10, "end_s": 20}, self.ALTS),
                         (True, True, 1))

    def test_within_default_tolerance(self):
        self.assertTrue(match_action({"name": "cut_range", "start_s": 0.4, "end_s": 10.3}, self.ALTS)[1])

    def test_right_name_wrong_params(self):
        self.assertEqual(match_action({"name": "cut_range", "start_s": 0, "end_s": 5}, self.ALTS),
                         (True, False, None))

    def test_wrong_name(self):
        self.assertEqual(match_action({"name": "mute_range", "start_s": 0, "end_s": 10}, self.ALTS),
                         (False, False, None))

    def test_missing_required_param_fails(self):
        self.assertFalse(match_action({"name": "cut_range", "start_s": 0}, self.ALTS)[1])

    def test_none_action(self):
        self.assertEqual(match_action(None, self.ALTS), (False, False, None))

    def test_rotate_degrees_alias(self):
        alts = [{"name": "rotate", "params": {"angle": 90}}]
        self.assertTrue(match_action({"name": "rotate", "degrees": 90}, alts)[1])

    def test_string_params_case_insensitive(self):
        alts = [{"name": "add_text", "params": {"text": "Summer Vlog", "align": "top"}}]
        self.assertTrue(match_action({"name": "add_text", "text": "summer vlog", "align": "TOP"}, alts)[1])

    def test_per_alternative_tolerance(self):
        alts = [{"name": "cut_range", "params": {"start_s": 12, "end_s": 15.5}, "tol": 1.0}]
        self.assertTrue(match_action({"name": "cut_range", "start_s": 12.8, "end_s": 14.7}, alts)[1])

    def test_extra_params_ignored(self):
        self.assertTrue(match_action({"name": "grayscale", "factor": 3}, [{"name": "grayscale"}])[1])


class Stats(unittest.TestCase):
    def test_wilson_bounds(self):
        lo, hi = wilson(5, 5)
        self.assertAlmostEqual(hi, 1.0, places=6)
        self.assertLess(lo, 0.6)  # 5/5 is NOT strong evidence of ~100%
        self.assertEqual(wilson(0, 0), (0.0, 0.0))

    def test_wilson_narrows_with_n(self):
        w_small = wilson(9, 10)
        w_big = wilson(90, 100)
        self.assertLess(w_big[1] - w_big[0], w_small[1] - w_small[0])

    def test_percentile(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], 0.5), 3)
        self.assertIsNone(percentile([], 0.5))
        self.assertEqual(percentile([None, 7], 0.95), 7)

    def test_aggregate_groups_and_counts(self):
        rows = [
            {"category": "cut", "outcome_pass": True, "action_ok": True, "schema_valid": True, "latency_ms": 100},
            {"category": "cut", "outcome_pass": False, "action_ok": False, "schema_valid": True, "latency_ms": 300,
             "forbidden_hit": True},
            {"category": "style", "outcome_pass": True},
        ]
        agg = aggregate(rows)
        self.assertEqual(agg["overall"]["outcome"]["k"], 2)
        self.assertEqual(agg["overall"]["outcome"]["n"], 3)
        self.assertEqual(agg["by_category"]["cut"]["outcome"]["k"], 1)
        self.assertEqual(agg["overall"]["forbidden_hits"], 1)
        self.assertEqual(agg["overall"]["action"]["n"], 2)  # rows without action_ok are unscored


if __name__ == "__main__":
    unittest.main()
