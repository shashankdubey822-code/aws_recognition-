import pytest
import sqlite3
from fastapi.testclient import TestClient
from app import app
from core.state import DB_PATH

def test_bulk_routes_registered():
    """Verify all 5 bulk registration endpoints are registered on the FastAPI app."""
    client = TestClient(app)
    
    # Check that route paths exist in app routes
    route_paths = [route.path for route in app.routes]
    assert "/api/bulk/crop" in route_paths
    assert "/api/bulk/cluster" in route_paths
    assert "/api/bulk/remove_crop" in route_paths
    assert "/api/bulk/push_person" in route_paths
    assert "/api/bulk/push_all" in route_paths
    assert "/api/bulk/clear_session" in route_paths

def test_safety_existing_students_not_touched():
    """Verify that calling bulk endpoints without valid sessions doesn't alter existing students in DB."""
    client = TestClient(app)
    
    # Check table count if table exists
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM registered_faces")
        initial_count = cursor.fetchone()[0]
    except Exception:
        initial_count = 0
    finally:
        conn.close()

    # Attempt cluster on non-existent session
    res = client.post("/api/bulk/cluster", json={"session_id": "fake_nonexistent"})
    assert res.status_code == 200
    assert res.json()["success"] is False

    # Attempt push on non-existent session
    res = client.post("/api/bulk/push_person", json={
        "session_id": "fake_nonexistent",
        "cluster_id": "cluster_1",
        "person_name": "Test Person",
        "person_roll": "123"
    })
    assert res.status_code == 200
    assert res.json()["success"] is False

    # Ensure DB count unchanged
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM registered_faces")
        after_count = cursor.fetchone()[0]
    except Exception:
        after_count = 0
    finally:
        conn.close()

    assert initial_count == after_count
