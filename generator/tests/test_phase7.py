"""Phase 7 resolution, lifecycle, survey, metrics, and integrated persistence tests."""

import unittest
from decimal import Decimal

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

import backend.models
from backend.models.complaint import Complaint, ComplaintReopenHistory, ComplaintStatusHistory
from backend.models.resolution import Resolution
from backend.models.survey import Survey
from backend.models.id_generators import generate_resolution_id
from generator.config import RANDOM_SEED
from generator.metrics import calculate_resolution_feedback_metrics
from generator.phase7 import Phase7Dataset, generate_phase7_dataset
from generator.resolutions import RESOLUTION_TYPES, extract_refund_amount, validate_resolutions
from generator.surveys import validate_surveys


def _resolution_snapshot(dataset: Phase7Dataset) -> tuple[object, ...]:
    """Return deterministic resolution, lifecycle, and survey data for repeatability checks."""
    return (
        tuple(
            (row.id, row.complaint_id, row.resolution_type, row.resolved_at, row.customer_notes)
            for row in dataset.resolutions
        ),
        tuple(
            (
                complaint.id,
                complaint.status,
                complaint.updated_at,
                tuple((event.from_status, event.to_status, event.changed_at) for event in complaint.status_history),
                tuple(
                    (event.reopen_sequence, event.previous_resolution_id, event.reopened_at)
                    for event in complaint.reopen_history
                ),
            )
            for complaint in dataset.phase6.complaints
        ),
        tuple(
            (survey.id, survey.complaint_id, survey.rating, survey.feedback_comments, survey.submitted_at)
            for survey in dataset.surveys
        ),
    )


class Phase7GeneratorTests(unittest.TestCase):
    """Generate Starter and Full Phase 7 graphs once, then validate all lifecycle contracts."""

    @classmethod
    def setUpClass(cls) -> None:
        """Generate complete deterministic Phase 7 datasets without database persistence."""
        cls.starter = generate_phase7_dataset("starter", seed=RANDOM_SEED)
        cls.full = generate_phase7_dataset("full", seed=RANDOM_SEED)

    def test_starter_and_full_resolution_history_and_survey_counts(self) -> None:
        """Both modes resolve only eligible cases and retain chronological history counts."""
        self.assertEqual(len(self.starter.resolutions), 10)
        self.assertEqual(len(self.starter.surveys), 6)
        self.assertEqual(len(self.full.resolutions), 684)
        self.assertEqual(len(self.full.surveys), 401)
        for dataset in (self.starter, self.full):
            self.assertTrue(all(resolution.resolution_type in RESOLUTION_TYPES for resolution in dataset.resolutions))
            status_history_count = sum(len(complaint.status_history) for complaint in dataset.phase6.complaints)
            self.assertGreaterEqual(status_history_count, len(dataset.phase6.complaints))
            self.assertEqual(
                sum(len(complaint.reopen_history) for complaint in dataset.phase6.complaints),
                1 if dataset is self.starter else 90,
            )

    def test_resolution_cardinality_and_refund_amounts(self) -> None:
        """Closed complaints have one final resolution; reopened cases retain one earlier attempt."""
        for dataset in (self.starter, self.full):
            complaints = dataset.phase6.complaints
            validate_resolutions(complaints, dataset.resolutions)
            by_complaint: dict[str, list[Resolution]] = {}
            for resolution in dataset.resolutions:
                by_complaint.setdefault(resolution.complaint_id, []).append(resolution)
                self.assertEqual(resolution.id, generate_resolution_id(resolution.complaint_id, resolution.attempt_number))
            for complaint in complaints:
                attempts = by_complaint.get(complaint.id, [])
                if complaint.status == "Closed":
                    self.assertEqual(len(attempts), 1)
                elif complaint.status == "Reopened":
                    self.assertEqual(len(attempts), 1)  # Historical attempt, not a final current resolution.
                else:
                    self.assertEqual(attempts, [])
            for resolution in dataset.resolutions:
                if resolution.resolution_type == "Refund":
                    amount = extract_refund_amount(resolution)
                    self.assertGreater(amount, Decimal("0.00"))
                    self.assertLessEqual(amount, resolution.complaint.order.total_amount)

    def test_closure_reopen_and_survey_chronology(self) -> None:
        """Reopened complaints have resolution < close < reopen; surveys follow final closure."""
        for dataset in (self.starter, self.full):
            resolution_by_id = {resolution.id: resolution for resolution in dataset.resolutions}
            for complaint in dataset.phase6.complaints:
                history = complaint.status_history
                self.assertEqual(history[-1].to_status, complaint.status)
                self.assertEqual(
                    [event.changed_at for event in history],
                    sorted(event.changed_at for event in history),
                )
                if complaint.status == "Reopened":
                    reopen = complaint.reopen_history[0]
                    previous_resolution = resolution_by_id[reopen.previous_resolution_id]
                    closed_at = next(event.changed_at for event in history if event.to_status == "Closed")
                    reopened_at = next(event.changed_at for event in history if event.to_status == "Reopened")
                    self.assertLess(previous_resolution.resolved_at, closed_at)
                    self.assertLess(closed_at, reopened_at)
                    self.assertEqual(reopen.reopened_at, reopened_at)
            validate_surveys(dataset.surveys, dataset.phase6.complaints)
            eligible_ids = {
                complaint.id for complaint in dataset.phase6.complaints
                if complaint.status in ("Resolved", "Closed")
            }
            self.assertTrue(all(survey.complaint_id in eligible_ids for survey in dataset.surveys))
            self.assertTrue(any(survey.rating <= 2 for survey in dataset.surveys))
            self.assertTrue(any(survey.rating >= 4 for survey in dataset.surveys))

    def test_metrics_use_generated_records(self) -> None:
        """All report metrics match independent calculations over generated outcomes."""
        for dataset in (self.starter, self.full):
            complaints = dataset.phase6.complaints
            resolutions = dataset.resolutions
            surveys = dataset.surveys
            metrics = calculate_resolution_feedback_metrics(complaints, resolutions, surveys)
            resolved_count = sum(complaint.status in ("Resolved", "Closed") for complaint in complaints)
            reopened_count = sum(complaint.status == "Reopened" for complaint in complaints)
            self.assertEqual(metrics["total_resolved_complaints"], resolved_count)
            self.assertEqual(metrics["total_unresolved_complaints"], len(complaints) - resolved_count)
            self.assertEqual(metrics["reopened_complaint_count"], reopened_count)
            self.assertEqual(metrics["survey_response_count"], len(surveys))
            self.assertEqual(metrics["positive_feedback_count"], sum(survey.rating >= 4 for survey in surveys))
            self.assertEqual(metrics["negative_feedback_count"], sum(survey.rating <= 2 for survey in surveys))
            self.assertEqual(
                metrics["refund_amount_total"],
                sum((extract_refund_amount(row) for row in resolutions), start=Decimal("0.00")),
            )
            self.assertEqual(dataset.metrics, metrics)

    def test_same_seed_reproduces_resolution_lifecycle_and_feedback(self) -> None:
        """The same seed reproduces resolution outcomes, lifecycle history, and survey answers."""
        second = generate_phase7_dataset("starter", seed=RANDOM_SEED)
        self.assertEqual(_resolution_snapshot(self.starter), _resolution_snapshot(second))

    def test_end_to_end_foreign_keys_and_round_trip_in_memory(self) -> None:
        """The full dependency graph and Phase 7 history rows insert and retrieve in SQLite memory."""
        dataset = generate_phase7_dataset("starter", seed=RANDOM_SEED)
        phase6 = dataset.phase6
        engine = create_engine("sqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        try:
            backend.models.Base.metadata.create_all(engine)
            SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
            with SessionFactory() as session:
                session.add_all(phase6.customers)
                session.add_all(phase6.products)
                session.add_all(phase6.orders)
                session.add_all(phase6.complaints)
                session.add_all(phase6.agents)
                session.add_all(phase6.assignments)
                session.add_all(phase6.messages)
                session.add_all(phase6.sla_clocks)
                session.add_all(phase6.sla_events)
                session.add_all(dataset.resolutions)
                session.add_all(dataset.surveys)
                session.commit()
                self.assertEqual(session.scalar(select(func.count()).select_from(Resolution)), len(dataset.resolutions))
                self.assertEqual(session.scalar(select(func.count()).select_from(Survey)), len(dataset.surveys))
                self.assertEqual(
                    session.scalar(select(func.count()).select_from(ComplaintStatusHistory)),
                    sum(len(complaint.status_history) for complaint in phase6.complaints),
                )
                self.assertEqual(
                    session.scalar(select(func.count()).select_from(ComplaintReopenHistory)),
                    sum(len(complaint.reopen_history) for complaint in phase6.complaints),
                )
                reopened = next(complaint for complaint in phase6.complaints if complaint.status == "Reopened")
                stored = session.get(Complaint, reopened.id)
                self.assertEqual(stored.status, "Reopened")
                self.assertTrue(stored.resolutions)
                self.assertEqual(stored.reopen_history[0].previous_resolution_id, stored.resolutions[0].id)
                surveyed = next(complaint for complaint in phase6.complaints if complaint.survey is not None)
                stored_surveyed = session.get(Complaint, surveyed.id)
                self.assertIsNotNone(stored_surveyed.survey)
                self.assertEqual(
                    session.connection().exec_driver_sql("PRAGMA foreign_key_check").all(),
                    [],
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
