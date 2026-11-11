"""Cross-entity baseline validation, reporting, and resolution-rate tests."""

import unittest

from generator.metrics import calculate_resolution_feedback_metrics
from generator.export import dataset_tables
from generator.phase8 import generate_complete_dataset
from generator.validation import validate_complete_dataset


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.starter = generate_complete_dataset("starter")
        cls.full = generate_complete_dataset("full")

    def test_starter_and_full_counts_and_reports(self):
        for dataset, expected in ((self.starter, 20), (self.full, 2000)):
            self.assertEqual(len(dataset.phase7.phase6.complaints), expected)
            report = validate_complete_dataset(dataset)
            self.assertEqual(report.failed_checks, 0, report.errors)
            self.assertEqual(report.passed_checks, report.total_checks)
            self.assertEqual(report.entity_counts["sla_clocks"], expected)

    def test_reproducible_baseline_and_ground_truth_separation(self):
        second = generate_complete_dataset("starter")
        self.assertEqual(self.starter.ground_truth, second.ground_truth)
        self.assertEqual(self.starter.validation.entity_counts, second.validation.entity_counts)
        self.assertEqual({x.complaint_id for x in self.starter.ground_truth}, {x.id for x in self.starter.phase7.phase6.complaints})
        self.assertTrue(all(x.expected_category for x in self.starter.ground_truth))
        self.assertTrue(any(x.expected_category != c.category.name for x, c in zip(self.starter.ground_truth, self.starter.phase7.phase6.complaints)))
        self.assertTrue(all(x.expected_repeat == bool(x.repeat_of_complaint_id) for x in self.starter.ground_truth))
        self.assertFalse(any("expected_" in col.name for col in self.starter.phase7.phase6.complaints[0].__table__.columns))
        full_again = generate_complete_dataset("full")
        self.assertEqual(dataset_tables(self.full), dataset_tables(full_again))

    def test_resolution_rate_uses_closed_complaints_over_all_complaints(self):
        for dataset in (self.starter, self.full):
            phase7 = dataset.phase7
            complaints = phase7.phase6.complaints
            resolved = sum(c.status in ("Resolved", "Closed") for c in complaints)
            expected = round(resolved * 100 / len(complaints), 2)
            metrics = calculate_resolution_feedback_metrics(complaints, phase7.resolutions, phase7.surveys)
            self.assertEqual(float(metrics["resolution_rate_percent"]), expected)
            self.assertEqual(metrics["total_resolved_complaints"], resolved)
            # Historical attempts on subsequently reopened cases explain count > current closed count.
            self.assertGreaterEqual(len(phase7.resolutions), resolved)


if __name__ == "__main__": unittest.main()
