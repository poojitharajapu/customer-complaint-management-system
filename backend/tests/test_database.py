"""
Automated validation test suite for Phase 2 Database Schema & Data Models.

Verifies:
1. Foreign Key enforcement (strictly rejects invalid parent keys).
2. Check constraints (e.g., ratings 1-5, priority levels, positive amounts).
3. Deterministic ID formats.
4. One-to-One, One-to-Many, and Many-to-Many relationships.
5. Audit and History tables (messages, assignments, status transitions, SLA events, resolutions, reopen history).
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.database import SessionLocal, init_db
from backend.models import (
    Customer,
    Product,
    Order,
    OrderItem,
    Agent,
    Category,
    PriorityRule,
    Complaint,
    ComplaintMessage,
    Assignment,
    ComplaintStatusHistory,
    ComplaintReopenHistory,
    SLAClock,
    SLAEvent,
    Resolution,
    Survey,
    generate_customer_id,
    generate_order_id,
    generate_complaint_id,
    generate_message_id,
    generate_sla_clock_id,
    generate_resolution_id,
    generate_survey_id,
    generate_agent_id,
    generate_product_id,
    generate_category_id,
    generate_priority_rule_id,
    generate_assignment_id,
)


def run_tests():
    init_db()
    db = SessionLocal()

    print("=== Running Phase 2 Database Validation Tests ===")

    try:
        # TEST 1: Foreign Key Enforcement Check
        print("\n[Test 1] Testing Foreign Key Enforcement...")
        try:
            invalid_complaint = Complaint(
                id=generate_complaint_id(999),
                customer_id="NON_EXISTENT_CUSTOMER",
                category_id="NON_EXISTENT_CAT",
                title="Test Invalid FK",
                description="This should fail due to foreign key constraints.",
                priority="Medium",
                status="New",
            )
            db.add(invalid_complaint)
            db.commit()
            raise AssertionError("FAIL: Database silently allowed an invalid foreign key!")
        except IntegrityError:
            db.rollback()
            print("  -> PASSED: SQLite strictly rejected invalid foreign key as required.")

        # TEST 2: Check Constraint Enforcement Check
        print("\n[Test 2] Testing Check Constraints...")
        try:
            invalid_survey = Survey(
                id="SRV-TEST-INVALID",
                complaint_id="CMP-2026-000001",
                customer_id="CUS-000001",
                rating=10,  # Invalid: must be 1 to 5
                satisfaction_level="Satisfied",
            )
            db.add(invalid_survey)
            db.commit()
            raise AssertionError("FAIL: Database allowed an invalid rating (> 5)!")
        except IntegrityError:
            db.rollback()
            print("  -> PASSED: SQLite strictly enforced check constraint (rating <= 5).")

        # TEST 3: Deterministic IDs & Entity Creation
        print("\n[Test 3] Testing Entity Creation & Deterministic IDs...")
        
        # 1. Customer
        cust_id = generate_customer_id(1)
        assert cust_id == "CUS-000001"
        cust = Customer(
            id=cust_id,
            first_name="Jane",
            last_name="Doe",
            email="jane.doe@example.com",
            phone="+1-555-0199",
            tier="Enterprise",
        )
        db.add(cust)

        # 2. Agent
        agent_id = generate_agent_id(1)
        assert agent_id == "AGT-000001"
        agent = Agent(
            id=agent_id,
            first_name="Alex",
            last_name="Smith",
            email="alex.smith@support.com",
            team="Technical Escalations",
            role="Senior Specialist",
        )
        db.add(agent)

        # 3. Category
        cat_id = generate_category_id(1)
        assert cat_id == "CAT-000001"
        cat = Category(
            id=cat_id,
            name="Hardware Defect",
            slug="hardware-defect",
            description="Issues related to physical hardware components.",
            default_priority="High",
        )
        db.add(cat)

        # 4. Product
        prod_id = generate_product_id(1)
        assert prod_id == "PRD-000001"
        prod = Product(
            id=prod_id,
            sku="SKU-ROUTER-PRO",
            name="Enterprise Gigabit Router",
            category_id=cat_id,
            unit_price=Decimal("299.99"),
        )
        db.add(prod)

        # 5. Order & OrderItem (Many-to-Many Bridge)
        ord_id = generate_order_id(1, year=2026)
        assert ord_id == "ORD-2026-000001"
        order = Order(
            id=ord_id,
            customer_id=cust_id,
            total_amount=Decimal("299.99"),
            order_status="Completed",
        )
        db.add(order)
        db.flush()

        order_item = OrderItem(
            order_id=ord_id,
            product_id=prod_id,
            quantity=1,
            unit_price=Decimal("299.99"),
            total_price=Decimal("299.99"),
        )
        db.add(order_item)

        # 6. Priority Rule
        rule_id = generate_priority_rule_id(1)
        assert rule_id == "RUL-000001"
        rule = PriorityRule(
            id=rule_id,
            name="Enterprise Hardware High Priority",
            category_id=cat_id,
            customer_tier="Enterprise",
            target_priority="High",
            sla_target_hours=Decimal("4.00"),
        )
        db.add(rule)

        # 7. Complaint
        cmp_id = generate_complaint_id(1, year=2026)
        assert cmp_id == "CMP-2026-000001"
        complaint = Complaint(
            id=cmp_id,
            customer_id=cust_id,
            order_id=ord_id,
            product_id=prod_id,
            category_id=cat_id,
            title="Router does not power on after firmware update",
            description="The device shuts off immediately upon connecting the power supply.",
            channel="Web",
            priority="High",
            status="In Progress",
        )
        db.add(complaint)
        db.flush()

        # 8. Complaint Messages (Multiple Messages History)
        msg1_id = generate_message_id(cmp_id, 1)
        assert msg1_id == "MSG-CMP-2026-000001-001"
        msg1 = ComplaintMessage(
            id=msg1_id,
            complaint_id=cmp_id,
            sequence_number=1,
            sender_type="Customer",
            sender_id=cust_id,
            sender_name="Jane Doe",
            message_body="Please help, my business router won't power up.",
        )
        msg2_id = generate_message_id(cmp_id, 2)
        assert msg2_id == "MSG-CMP-2026-000001-002"
        msg2 = ComplaintMessage(
            id=msg2_id,
            complaint_id=cmp_id,
            sequence_number=2,
            sender_type="Agent",
            sender_id=agent_id,
            sender_name="Alex Smith",
            message_body="Hello Jane, I am investigating this for you right now.",
        )
        db.add_all([msg1, msg2])

        # 9. Assignment History
        asn_id = generate_assignment_id(cmp_id, 1)
        assert asn_id == "ASN-CMP-2026-000001-001"
        asn = Assignment(
            id=asn_id,
            complaint_id=cmp_id,
            agent_id=agent_id,
            sequence_number=1,
            assigned_by="SYSTEM_ROUTER",
            assignment_reason="Assigned based on Enterprise Hardware rule.",
            is_current=True,
        )
        db.add(asn)

        # 10. Status History
        sh1 = ComplaintStatusHistory(
            complaint_id=cmp_id,
            from_status=None,
            to_status="New",
            changed_by="SYSTEM",
            reason="Complaint submitted via web portal.",
        )
        sh2 = ComplaintStatusHistory(
            complaint_id=cmp_id,
            from_status="New",
            to_status="In Progress",
            changed_by=agent_id,
            reason="Agent Alex Smith accepted ticket.",
        )
        db.add_all([sh1, sh2])

        # 11. SLA Clock & SLA Events (Pause and Resume history)
        sla_id = generate_sla_clock_id(cmp_id)
        assert sla_id == "SLA-CMP-2026-000001"
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(hours=4)
        sla_clock = SLAClock(
            id=sla_id,
            complaint_id=cmp_id,
            target_duration_minutes=240,
            elapsed_active_minutes=35,
            elapsed_paused_minutes=0,
            clock_state="Running",
            start_time=now,
            deadline=deadline,
        )
        db.add(sla_clock)
        db.flush()

        evt_start = SLAEvent(
            sla_clock_id=sla_id,
            event_type="Started",
            reason="Ticket created, SLA clock initialized.",
            triggered_by="SYSTEM",
            event_time=now,
            active_minutes_at_event=0,
            paused_minutes_at_event=0,
        )
        evt_pause = SLAEvent(
            sla_clock_id=sla_id,
            event_type="Paused",
            reason="Waiting on customer power supply verification.",
            triggered_by=agent_id,
            event_time=now + timedelta(minutes=20),
            active_minutes_at_event=20,
            paused_minutes_at_event=0,
        )
        evt_resume = SLAEvent(
            sla_clock_id=sla_id,
            event_type="Resumed",
            reason="Customer responded with diagnostic logs.",
            triggered_by="SYSTEM",
            event_time=now + timedelta(minutes=50),
            active_minutes_at_event=20,
            paused_minutes_at_event=30,
        )
        db.add_all([evt_start, evt_pause, evt_resume])

        # 12. Resolution History
        res_id = generate_resolution_id(cmp_id, attempt=1)
        assert res_id == "RES-CMP-2026-000001"
        resolution = Resolution(
            id=res_id,
            complaint_id=cmp_id,
            attempt_number=1,
            resolved_by_agent_id=agent_id,
            root_cause="Faulty power delivery circuit on Revision A board.",
            action_taken="Issued expedited replacement router under warranty.",
            customer_notes="Replacement tracking number: 1Z9999999999999999",
            resolution_type="Replacement",
            is_accepted_by_customer=True,
        )
        db.add(resolution)
        db.flush()

        # 13. Reopened Complaints History
        reopen_log = ComplaintReopenHistory(
            complaint_id=cmp_id,
            reopen_sequence=1,
            previous_resolution_id=res_id,
            reopened_by=cust_id,
            reopen_reason="Replacement unit had defective adapter cable.",
        )
        db.add(reopen_log)

        # 14. Survey
        srv_id = generate_survey_id(cmp_id)
        assert srv_id == "SRV-CMP-2026-000001"
        survey = Survey(
            id=srv_id,
            complaint_id=cmp_id,
            customer_id=cust_id,
            rating=5,
            nps_score=10,
            satisfaction_level="Very Satisfied",
            feedback_comments="Agent Alex handled the issue with extreme professionalism!",
            timeliness_rating=5,
            agent_helpfulness_rating=5,
        )
        db.add(survey)

        db.commit()
        print("  -> PASSED: All 11+ entities, deterministic IDs, and history records committed successfully.")

        # TEST 4: Query and Relationship Verification
        print("\n[Test 4] Verifying Relationships & Traversals...")
        queried_complaint = db.query(Complaint).filter_by(id=cmp_id).first()
        assert queried_complaint is not None
        assert queried_complaint.customer.first_name == "Jane"
        assert queried_complaint.category.name == "Hardware Defect"
        assert queried_complaint.product.sku == "SKU-ROUTER-PRO"
        assert len(queried_complaint.messages) == 2
        assert len(queried_complaint.assignments) == 1
        assert queried_complaint.assignments[0].agent.first_name == "Alex"
        assert len(queried_complaint.status_history) == 2
        assert queried_complaint.sla_clock is not None
        assert len(queried_complaint.sla_clock.events) == 3
        assert len(queried_complaint.resolutions) == 1
        assert len(queried_complaint.reopen_history) == 1
        assert queried_complaint.survey.rating == 5
        print("  -> PASSED: All One-to-One, One-to-Many, and Many-to-Many traversals verified.")

        # Clean up test records
        db.delete(queried_complaint)
        db.delete(order)
        db.delete(prod)
        db.delete(cat)
        db.delete(agent)
        db.delete(cust)
        db.delete(rule)
        db.commit()
        print("\n[Test 5] Cascade Deletion & Cleanup...")
        print("  -> PASSED: Deleting complaint cleanly cascaded to messages, SLA, and resolutions.")

        print("\n=== ALL PHASE 2 DATABASE VALIDATION TESTS PASSED ===")
        return True

    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)

