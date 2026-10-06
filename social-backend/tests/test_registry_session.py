"""
The Registry tab signs in to the copyright registry as the current VibeSocial user,
brokered server-side, so there is one account per creator instead of two.
"""
import requests


def test_requires_social_login(client, mock_registry):
    mock_registry(json_response={"access_token": "x"})
    assert client.post("/api/registry/session").status_code == 401


def test_vouches_for_the_signed_in_username_not_a_client_supplied_one(client, auth_headers, mock_registry):
    """
    The username sent to the registry must come from the verified VibeSocial session.
    If the client could name the user, anyone could obtain a registry session -- and
    thus register content -- as somebody else.
    """
    mock_registry(json_response={"access_token": "reg-token", "username": auth_headers["username"]})

    resp = client.post(
        "/api/registry/session",
        headers=auth_headers["headers"],
        data={"username": "someone_else"},  # must be ignored
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "reg-token"

    sent = mock_registry.calls[-1]
    assert sent["url"].endswith("/internal/session")
    assert sent["kwargs"]["data"] == {"username": auth_headers["username"]}


def test_authenticates_to_the_registry_with_the_internal_key(client, auth_headers, mock_registry):
    mock_registry(json_response={"access_token": "reg-token"})
    client.post("/api/registry/session", headers=auth_headers["headers"])
    assert "x-registry-internal" in mock_registry.calls[-1]["kwargs"]["headers"]


def test_registry_down_returns_clean_503(client, auth_headers, mock_registry):
    mock_registry(exception=requests.exceptions.ConnectionError("registry down"))
    resp = client.post("/api/registry/session", headers=auth_headers["headers"])
    assert resp.status_code == 503


def test_registry_rejection_returns_clean_503(client, auth_headers, mock_registry):
    mock_registry(json_response={"detail": "Forbidden"}, status_code=403)
    resp = client.post("/api/registry/session", headers=auth_headers["headers"])
    assert resp.status_code == 503


def test_registry_account_conflict_is_passed_through(client, auth_headers, mock_registry):
    mock_registry(json_response={"detail": "A separate CopyGuard account already uses this username"}, status_code=409)
    resp = client.post("/api/registry/session", headers=auth_headers["headers"])
    assert resp.status_code == 409
    assert "separate CopyGuard account" in resp.json()["detail"]
