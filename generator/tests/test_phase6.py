"""Phase 6 generator and integrated SQLAlchemy graph tests."""

import unittest
from datetime import timedelta

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # Register the complete relationship graph.
from backend.models.agent import Agent
from backend.models.assignment import Assignment
from backend.models.complaint import Complaint
from backend.models.complaint_message import ComplaintMessage
from backend.models.order import Order
from backend.models.sla import SLAClock, SLAEvent
from generator.agents import FULL_AGENT_COUNT, STARTER_AGENT_COUNT, generate_agents, validate_agents
from generator.assignments import generate_assignments, team_for_complaint, validate_assignments
from generator.config import RANDOM_SEED
from generator.messages import generate_messages, validate_messages
from generator.phase6 import generate_phase6_dataset
from generator.sla_events import generate_sla_events, validate_sla_events
from generator.slas import SLA_TARGET_HOURS, calculate_deadline, generate_slas, sla_target_minutes, validate_slas


class Phase6GeneratorTests(unittest.TestCase):
    """Build Starter and Full datasets once for focused module and integration assertions."""

    @classmethod
    def setUpClass(cls) -> None:
        """Generate dependency-ordered datasets using in-memory model objects only."""
        cls.starter = generate_phase6_dataset("starter", seed=RANDOM_SEED)
        cls.full = generate_phase6_dataset("full", seed=RANDOM_SEED)

    def test_agent_counts_unique_ids_emails_and_seed(self) -> None:
        """Starter/Full agent counts, synthetic emails, and deterministic IDs are correct."""
        self.assertEqual(len(self.starter.agents), STARTER_AGENT_COUNT)
        self.assertEqual(len(self.full.agents), FULL_AGENT_COUNT)
        for agents in (self.starter.agents, self.full.agents):
            validate_agents(agents)
            self.assertEqual(len({agent.id for agent in agents}), len(agents))
            self.assertEqual(len({agent.email for agent in agents}), len(agents))
            for team in ("Technical Support", "Billing", "Delivery", "General Support", "Safety"):
                self.assertTrue(any(agent.team == team and agent.is_active for agent in agents))
        repeat = generate_agents("starter", seed=RANDOM_SEED)
        self.assertEqual(
            [(agent.id, agent.email, agent.team, agent.is_active) for agent in repeat],
            [(agent.id, agent.email, agent.team, agent.is_active) for agent in self.starter.agents],
        )

    def test_message_counts_ids_references_and_timestamps(self) -> None:
        """Messages reach configured counts with valid sender IDs and ordered threads."""
        for dataset, expected_count in ((self.starter, 60), (self.full, 6_000)):
            self.assertEqual(len(dataset.messages), expected_count)
            self.assertEqual(len({message.id for message in dataset.messages}), expected_count)
            validate_messages(dataset.messages, dataset.complaints)
            complaint_ids = {complaint.id for complaint in dataset.complaints}
            agent_ids = {agent.id for agent in dataset.agents}
            for message in dataset.messages:
                self.assertIn(message.complaint_id, complaint_ids)
                if message.sender_type == "Agent":
                    self.assertIn(message.sender_id, agent_ids)
        regenerated = generate_messages(
            self.starter.complaints, self.starter.agents, self.starter.assignments, seed=RANDOM_SEED
        )
        self.assertEqual(
            [(item.id, item.sender_id, item.message_body, item.created_at) for item in regenerated],
            [(item.id, item.sender_id, item.message_body, item.created_at) for item in self.starter.messages],
        )

    def test_assignments_history_routing_and_active_agents(self) -> None:
        """All complaints have valid current routing and specialist reassignments are ordered."""
        for dataset in (self.starter, self.full):
            validate_assignments(dataset.assignments, dataset.complaints)
            agent_ids = {agent.id for agent in dataset.agents}
            complaint_ids = {complaint.id for complaint in dataset.complaints}
            self.assertGreaterEqual(len(dataset.assignments), len(dataset.complaints))
            self.assertTrue(any(assignment.sequence_number == 2 for assignment in dataset.assignments))
            for assignment in dataset.assignments:
                self.assertIn(assignment.complaint.id, complaint_ids)
                self.assertIn(assignment.agent.id, agent_ids)
                self.assertTrue(assignment.agent.is_active)
                self.assertGreaterEqual(assignment.assigned_at, assignment.complaint.created_at)
            safety = [complaint for complaint in dataset.complaints if complaint.category.name == "Safety Issue"]
            self.assertTrue(safety)
            for complaint in safety:
                current = [item for item in complaint.assignments if item.is_current]
                if current:
                    self.assertEqual(current[0].agent.team, "Safety")
                else:
                    self.assertEqual(complaint.assignments[-1].agent.team, "Safety")
                self.assertEqual(complaint.priority, "Critical")

    def test_sla_targets_due_dates_pause_resume_and_escalations(self) -> None:
        """SLA targets match priority and paused minutes extend deadlines without active accrual."""
        self.assertEqual(
            {priority: sla_target_minutes(priority) for priority in SLA_TARGET_HOURS},
            {"Critical": 240, "High": 480, "Medium": 1440, "Low": 4320},
        )
        self.assertEqual(
            calculate_deadline(self.starter.complaints[0].created_at, 240, 35),
            self.starter.complaints[0].created_at + timedelta(minutes=275),
        )
        for dataset in (self.starter, self.full):
            self.assertEqual(len(dataset.sla_clocks), len(dataset.complaints))
            validate_slas(dataset.sla_clocks, dataset.complaints)
            validate_sla_events(dataset.sla_events, dataset.sla_clocks)
            events_by_clock = {}
            for event in dataset.sla_events:
                events_by_clock.setdefault(event.sla_clock.id, []).append(event)
            self.assertTrue(any(clock.is_breached for clock in dataset.sla_clocks))
            self.assertTrue(any(clock.clock_state == "Paused" for clock in dataset.sla_clocks))
            self.assertTrue(any((event.reason or "").startswith("Escalation:") for event in dataset.sla_events))
            for clock in dataset.sla_clocks:
                self.assertEqual(clock.deadline, calculate_deadline(
                    clock.start_time, clock.target_duration_minutes, clock.elapsed_paused_minutes
                ))
                thread = events_by_clock[clock.id]
                pauses = [event for event in thread if event.event_type == "Paused"]
                resumes = [event for event in thread if event.event_type == "Resumed"]
                if pauses and resumes:
                    self.assertEqual(pauses[0].active_minutes_at_event, resumes[0].active_minutes_at_event)
                    self.assertGreater(resumes[0].paused_minutes_at_event, pauses[0].paused_minutes_at_event)
                elif pauses:
                    self.assertIn(clock.complaint.status, ("Pending Customer", "Pending Vendor"))
                    self.assertEqual(clock.clock_state, "Paused")

    def test_complete_pipeline_repeats_with_same_seed(self) -> None:
        """The integrated generator reproduces module outputs, statuses, dates, and events."""
        repeated = generate_phase6_dataset("starter", seed=RANDOM_SEED)
        self.assertEqual(
            [(agent.id, agent.email, agent.team, agent.created_at) for agent in repeated.agents],
            [(agent.id, agent.email, agent.team, agent.created_at) for agent in self.starter.agents],
        )
        self.assertEqual(
            [(item.id, item.agent.id, item.assigned_at, item.is_current) for item in repeated.assignments],
            [(item.id, item.agent.id, item.assigned_at, item.is_current) for item in self.starter.assignments],
        )
        self.assertEqual(
            [(item.id, item.sender_id, item.message_body, item.created_at) for item in repeated.messages],
            [(item.id, item.sender_id, item.message_body, item.created_at) for item in self.starter.messages],
        )
        self.assertEqual(
            [(clock.id, clock.deadline, clock.clock_state, clock.elapsed_active_minutes, clock.elapsed_paused_minutes) for clock in repeated.sla_clocks],
            [(clock.id, clock.deadline, clock.clock_state, clock.elapsed_active_minutes, clock.elapsed_paused_minutes) for clock in self.starter.sla_clocks],
        )
        self.assertEqual(
            [(item.sla_clock_id, item.event_type, item.event_time, item.active_minutes_at_event, item.paused_minutes_at_event) for item in repeated.sla_events],
            [(item.sla_clock_id, item.event_type, item.event_time, item.active_minutes_at_event, item.paused_minutes_at_event) for item in self.starter.sla_events],
        )

    def test_integrated_in_memory_foreign_keys_and_relationships(self) -> None:
        """All Phase 6 record types connect and round-trip in foreign-key-enforced SQLite."""
        dataset = self.starter
        engine = create_engine("sqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        try:
            backend.models.Base.metadata.create_all(engine)
            SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
            with SessionFactory() as session:
                session.add_all(dataset.customers)
                session.add_all(dataset.products)
                session.add_all(dataset.orders)
                session.add_all(dataset.complaints)
                session.add_all(dataset.agents)
                session.add_all(dataset.assignments)
                session.add_all(dataset.messages)
                session.add_all(dataset.sla_clocks)
                session.add_all(dataset.sla_events)
                session.commit()
                self.assertEqual(session.scalar(select(func.count()).select_from(Complaint)), 20)
                self.assertEqual(session.scalar(select(func.count()).select_from(Agent)), STARTER_AGENT_COUNT)
                self.assertEqual(session.scalar(select(func.count()).select_from(ComplaintMessage)), 60)
                self.assertEqual(session.scalar(select(func.count()).select_from(SLAClock)), 20)
                self.assertEqual(session.scalar(select(func.count()).select_from(SLAEvent)), len(dataset.sla_events))
                self.assertEqual(session.scalar(select(func.count()).select_from(Assignment)), len(dataset.assignments))
                retrieved = session.scalars(select(Complaint).order_by(Complaint.id)).all()
                self.assertIsNotNone(retrieved[0].customer)
                self.assertIsNotNone(retrieved[0].category)
                self.assertIsNotNone(retrieved[0].sla_clock)
                self.assertTrue(retrieved[0].messages)
                self.assertTrue(retrieved[0].assignments)
                self.assertEqual(
                    session.connection().exec_driver_sql("PRAGMA foreign_key_check").all(),
                    [],
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
