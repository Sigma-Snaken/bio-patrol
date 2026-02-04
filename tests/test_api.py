import sys
import os
os.environ["MOCK_BACKEND_API"] = "True"
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Hello Kachaka!"

def test_get_robots():
    resp = client.get("/kachaka/robots")
    assert resp.status_code == 200
    robots = resp.json()
    assert isinstance(robots, list)
    assert any("id" in r and "url" in r for r in robots)

# def test_create_task():
#     # This test assumes a minimal valid robot exists in robots.json
#     robot_id = "normal"
#     task_data = {
#         "task_id": "",  # Required by Task model
#         "robot_id": robot_id,
#         "steps": [
#             {"step_id": "1", "action": "speak", "params": {"speak_text": "Hello"}, "status": "pending"}
#         ],
#         "status": "queued"
#     }
#     resp = client.post("/api/tasks", json=task_data)
#     assert resp.status_code == 200
#     data = resp.json()
#     assert data["robot_id"] == robot_id
#     assert data["status"] in ["queued", "QUEUED"]

# Add more endpoint tests as needed
