"""FastAPI integration tests on isolated in-memory SQLite databases."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.dependencies import get_db
from backend.main import create_app
from backend.models import Agent, Base, Category, PriorityRule


@pytest.fixture
def api():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    timestamp = datetime.now(timezone.utc)
    with factory() as db:
        for i, (name, priority) in enumerate((("Safety Issue", "Critical"), ("Refund", "High"), ("Other", "Low")), start=1):
            category = Category(id=f"CAT-{i:06d}", name=name, slug=name.lower().replace(" ", "-"), default_priority=priority, is_active=True, created_at=timestamp, updated_at=timestamp)
            db.add(category)
            db.flush()
            db.add(PriorityRule(id=f"RUL-{i:06d}", name=f"{name} default", category=category, target_priority=priority, sla_target_hours={"Critical": 4, "High": 8, "Low": 72}[priority], is_active=True, created_at=timestamp, updated_at=timestamp))
        db.commit()

    app = create_app()

    def override_db():
        with factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client
    engine.dispose()


def new_customer(client, email="test@example.invalid"):
    return client.post("/api/v1/customers", json={"first_name": "Mira", "last_name": "Sample", "email": email}).json()


def new_safety_complaint(client, customer_id):
    return client.post("/api/v1/complaints", json={"customer_id": customer_id, "title": "Device sparked", "description": "The device sparked and produced smoke during use."})


def test_health_readiness_and_customer_crud_search_pagination(api):
    assert api.get("/").status_code == 200
    assert api.get("/health").json()["status"] == "healthy"
    assert api.get("/ready").json()["status"] == "ready"
    browser_response = api.get("/api/v1/dashboard/summary", headers={"Origin": "http://127.0.0.1:3000"})
    assert browser_response.status_code == 200
    assert browser_response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    customer = new_customer(api)
    assert customer["id"] == "CUS-000001"
    assert api.get("/api/v1/customers/CUS-000001").json()["email"] == "test@example.invalid"
    assert api.get("/api/v1/customers", params={"search": "Mira", "page": 1, "page_size": 1}).json()["total"] == 1
    assert api.patch("/api/v1/customers/CUS-000001", json={"tier": "Premium"}).json()["tier"] == "Premium"
    assert api.get("/api/v1/customers/CUS-404").status_code == 404


def test_validation_duplicate_rollback_and_invalid_customer_reference(api):
    new_customer(api)
    assert api.post("/api/v1/customers", json={"first_name": "Else", "last_name": "Same", "email": "test@example.invalid"}).status_code == 409
    assert api.get("/api/v1/customers").json()["total"] == 1
    assert api.post("/api/v1/customers", json={"first_name": "Bad", "last_name": "Email", "email": "not-an-email"}).status_code == 422
    invalid = new_safety_complaint(api, "CUS-MISSING")
    assert invalid.status_code == 404
    assert api.get("/api/v1/complaints").json()["total"] == 0


def test_complaint_classification_critical_safety_status_filters_and_history(api):
    customer = new_customer(api)
    complaint = new_safety_complaint(api, customer["id"])
    assert complaint.status_code == 201
    record = complaint.json()
    assert record["id"] == "CMP-2026-000001"
    assert record["category_name"] == "Safety Issue" and record["priority"] == "Critical"
    assert api.patch(f"/api/v1/complaints/{record['id']}", json={"title": "Safety device sparked again"}).json()["title"] == "Safety device sparked again"
    page = api.get("/api/v1/complaints", params={"category": "Safety Issue", "priority": "Critical", "page_size": 1}).json()
    assert page["total"] == 1 and page["items"][0]["id"] == record["id"]
    assert api.get(f"/api/v1/complaints/{record['id']}/history").json()[0]["to_status"] == "New"
    assert api.patch(f"/api/v1/complaints/{record['id']}/status", json={"status": "Pending Customer", "changed_by": "AGT-TEST"}).status_code == 200
    assert api.patch(f"/api/v1/complaints/{record['id']}/status", json={"status": "Closed", "changed_by": "AGT-TEST"}).status_code == 422


def test_agent_assignment_messages_sla_resolution_reopen_and_survey(api):
    customer = new_customer(api)
    complaint = new_safety_complaint(api, customer["id"]).json()
    agent = api.post("/api/v1/agents", json={"first_name": "Ari", "last_name": "Fiction", "email": "agent@example.invalid", "team": "Safety"}).json()
    assert agent["id"] == "AGT-000001"
    assert api.get("/api/v1/agents", params={"active_only": "true"}).json()["total"] == 1
    assignment = api.post(f"/api/v1/complaints/{complaint['id']}/assignments", json={"agent_id": agent["id"]})
    assert assignment.status_code == 201
    second_agent = api.post("/api/v1/agents", json={"first_name": "Bela", "last_name": "Fiction", "email": "agent2@example.invalid", "team": "Safety"}).json()
    reassigned = api.post(f"/api/v1/complaints/{complaint['id']}/assignments", json={"agent_id": second_agent["id"]})
    assert reassigned.status_code == 201
    inactive_agent = api.post("/api/v1/agents", json={"first_name": "Caro", "last_name": "Fiction", "email": "agent3@example.invalid", "team": "Safety", "is_active": False}).json()
    assert api.post(f"/api/v1/complaints/{complaint['id']}/assignments", json={"agent_id": inactive_agent["id"]}).status_code == 409
    history = api.get(f"/api/v1/complaints/{complaint['id']}/assignments").json()
    assert len(history) == 2 and history[0]["is_current"] is False and history[1]["is_current"] is True
    message = api.post(f"/api/v1/complaints/{complaint['id']}/messages", json={"sender_type": "Customer", "sender_id": customer["id"], "message_body": "More details."})
    assert message.status_code == 201
    agent_message = api.post(f"/api/v1/complaints/{complaint['id']}/messages", json={"sender_type": "Agent", "sender_id": second_agent["id"], "message_body": "We are reviewing this."})
    assert agent_message.status_code == 201
    assert len(api.get(f"/api/v1/complaints/{complaint['id']}/messages").json()) == 2
    before = api.get(f"/api/v1/slas/{complaint['id']}").json()
    assert before["target_duration_minutes"] == 240
    assert api.post(f"/api/v1/slas/{complaint['id']}/pause").json()["clock_state"] == "Paused"
    resumed = api.post(f"/api/v1/slas/{complaint['id']}/resume")
    assert resumed.status_code == 200 and resumed.json()["deadline"] >= before["deadline"]
    assert api.post(f"/api/v1/slas/{complaint['id']}/escalate", params={"reason": "Safety review requested"}).status_code == 200
    assert api.post(f"/api/v1/complaints/{complaint['id']}/surveys", json={"customer_id": customer["id"], "rating": 5}).status_code == 409
    refund_without_order = api.post(f"/api/v1/complaints/{complaint['id']}/resolutions", json={"resolved_by_agent_id": agent["id"], "resolution_type": "Refund", "root_cause": "Incorrect shipment", "action_taken": "Refund initiated", "refund_amount": "1.00"})
    assert refund_without_order.status_code == 422
    resolution = api.post(f"/api/v1/complaints/{complaint['id']}/resolutions", json={"resolved_by_agent_id": agent["id"], "resolution_type": "Replacement", "root_cause": "Unsafe unit", "action_taken": "Replacement arranged"})
    assert resolution.status_code == 201 and resolution.json()["status"] == "Closed"
    survey = api.post(f"/api/v1/complaints/{complaint['id']}/surveys", json={"customer_id": customer["id"], "rating": 5, "nps_score": 9})
    assert survey.status_code == 201
    reopened = api.post(f"/api/v1/complaints/{complaint['id']}/reopen", json={"reopened_by": customer["id"], "reason": "Issue returned"})
    assert reopened.status_code == 200 and reopened.json()["status"] == "Reopened"
    assert len(api.get(f"/api/v1/complaints/{complaint['id']}/resolutions").json()) == 1
    assert api.get("/api/v1/metrics/customer-satisfaction").json()["survey_response_count"] == 1
    assert len(api.get(f"/api/v1/slas/{complaint['id']}/events").json()) >= 5
    dashboard = api.get("/api/v1/dashboard/summary").json()
    assert dashboard["total_complaints"] == 1 and dashboard["open_complaints"] == 1
    assert dashboard["reopened_complaint_count"] == 1 and dashboard["customer_satisfaction_average"] == 5
    second_resolution = api.post(f"/api/v1/complaints/{complaint['id']}/resolutions", json={"resolved_by_agent_id": agent["id"], "resolution_type": "Explanation Provided", "root_cause": "Follow-up report", "action_taken": "Additional safety review completed"})
    assert second_resolution.status_code == 201
    history = api.get(f"/api/v1/complaints/{complaint['id']}/resolutions").json()
    assert len(history) == 2 and history[0]["id"] == resolution.json()["id"]
    assert api.get(f"/api/v1/complaints/{complaint['id']}/assignments").json()[-1]["is_current"] is False


def test_dashboard_metrics_and_breach_routes(api):
    assert api.get("/api/v1/dashboard/summary").json()["total_complaints"] == 0
    assert api.get("/api/v1/slas/breached").json() == []
    assert api.get("/api/v1/slas/at-risk").status_code == 200
