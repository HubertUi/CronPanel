"""Tests for the health check endpoint."""


def test_health_returns_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["app"] == "CronPanel"
    assert body["timestamp"]


def test_unknown_api_route_returns_structured_404(client, seeded_db, auth_headers):
    response = client.get("/api/does-not-exist", headers=auth_headers)

    assert response.status_code == 404
