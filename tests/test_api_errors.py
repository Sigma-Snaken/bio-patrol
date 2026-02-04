import os
os.environ["MOCK_BACKEND_API"] = "True"
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# --- Robot endpoints ---
def test_get_all_robots():
    resp = client.get("/kachaka/robots")
    assert resp.status_code == 200
    robots = resp.json()
    # Strictly check for mock mode expected data
    expected = [
        {"id": "normal", "url": "192.168.204.37:26400", "name": "Sigma 01"},
        {"id": "pro", "url": "192.168.204.38:26400", "name": "Sigma 02"}
    ]
    if isinstance(robots, list):
        assert robots == expected
    elif isinstance(robots, dict):
        # Accept dict-of-robots for legacy reasons
        values = list(robots.values())
        assert values == expected
    else:
        assert False, f"Unexpected robots type: {type(robots)}"

