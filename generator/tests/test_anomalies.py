"""Focused tests for isolated, intentionally invalid anomaly examples."""

import unittest

from generator.anomalies import detect_anomaly, generate_anomalies


class AnomalyTests(unittest.TestCase):
    def test_all_six_anomaly_scenarios_are_independently_detectable(self):
        rows = generate_anomalies()
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({row.id for row in rows}), 6)
        self.assertEqual({row.anomaly_type for row in rows}, {
            "invalid_customer_fk", "resolution_before_creation", "incorrect_sla_pause_math",
            "unlinked_repeat", "safety_low_queue", "survey_before_closure",
        })
        self.assertTrue(all(row.intentionally_invalid and row.ground_truth_label == "invalid" for row in rows))
        self.assertTrue(all(detect_anomaly(row) for row in rows))


if __name__ == "__main__": unittest.main()
