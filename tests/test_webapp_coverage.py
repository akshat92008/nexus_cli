"""Tests for WebApp server coverage."""

import pytest
from starlette.testclient import TestClient

from nexus.webapp.server import create_app


@pytest.fixture
def client():
    app = create_app("dummy-api-key")
    return TestClient(app)


def test_webapp_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "window.CSRF_TOKEN" in response.text


def test_webapp_api_chat_unauthorized(client):
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 403


def test_webapp_api_chat_empty(client):
    # Need to access the module to get the generated token for the test
    from nexus.webapp.server import _web_token

    response = client.post("/api/chat", json={}, headers={"X-CSRF-Token": _web_token})
    assert response.status_code == 400
    assert "Empty message" in response.json()["error"]


def test_websocket_unauthorized(client):
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "chat", "message": "hello"})
        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "Unauthorized" in data["content"]


def test_websocket_authenticate(client):
    from nexus.webapp.server import _web_token

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "authenticate", "token": _web_token})
        # Doesn't return anything on success, so we send a model set
        websocket.send_json({"type": "set_model", "model": "invalid-model"})
        data = websocket.receive_json()
        assert data["type"] == "error"
