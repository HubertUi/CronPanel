"""Tests for the login rate limiter."""


def test_rate_limit_blocks_after_max_failures(client, seeded_db, admin_account):
    from app.core.rate_limit import login_rate_limiter

    # Force a very low threshold for this test.
    login_rate_limiter.max_events = 3

    username = admin_account["username"]

    # 3 failures should succeed but be counted.
    for _ in range(3):
        resp = client.post(
            "/api/auth/login",
            data={"username": username, "password": "wrong"},
        )
        assert resp.status_code == 401

    # 4th attempt — even with correct password — should be blocked.
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": admin_account["password"]},
    )
    assert resp.status_code == 429
    assert resp.json()["error"] == "RATE_LIMITED"
    assert "Retry-After" in resp.headers


def test_successful_login_resets_rate_limit(client, seeded_db, admin_account):
    from app.core.rate_limit import login_rate_limiter

    login_rate_limiter.max_events = 3

    username = admin_account["username"]

    # 1 failure
    client.post("/api/auth/login", data={"username": username, "password": "wrong"})
    # successful login resets counter
    client.post(
        "/api/auth/login",
        data={"username": username, "password": admin_account["password"]},
    )
    # next failure should still be allowed
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": "wrong"},
    )
    assert resp.status_code == 401  # not 429


def test_rate_limit_keyed_by_username(client, seeded_db):
    from app.core.rate_limit import login_rate_limiter

    login_rate_limiter.max_events = 2

    # Exhaust limit for a non-existent username.
    for _ in range(2):
        client.post("/api/auth/login", data={"username": "ghost1", "password": "wrong"})

    # Different username from the same IP should NOT be blocked.
    resp = client.post(
        "/api/auth/login",
        data={"username": "ghost2", "password": "wrong"},
    )
    assert resp.status_code == 401  # invalid creds, not rate limit
