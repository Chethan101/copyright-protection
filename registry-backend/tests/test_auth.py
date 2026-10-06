import jwt
import pytest

from app import auth


def test_register_success(client):
    resp = client.post("/api/register", data={"username": "alice", "password": "strongpass123"})
    assert resp.status_code == 200
    assert resp.json()["msg"] == "Registered successfully"


def test_register_duplicate_username_rejected(client):
    client.post("/api/register", data={"username": "alice", "password": "strongpass123"})
    resp = client.post("/api/register", data={"username": "alice", "password": "other12345"})
    assert resp.status_code == 400


def test_register_empty_username_rejected(client):
    resp = client.post("/api/register", data={"username": "   ", "password": "strongpass123"})
    assert resp.status_code == 400


def test_register_short_password_rejected(client):
    resp = client.post("/api/register", data={"username": "bob", "password": "short"})
    assert resp.status_code == 400


def test_login_success(client, register_user):
    username, password = register_user()
    resp = client.post("/api/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_rejected(client, register_user):
    username, _ = register_user()
    resp = client.post("/api/login", data={"username": username, "password": "wrong-password"})
    assert resp.status_code == 400


def test_login_unknown_user_rejected(client):
    resp = client.post("/api/login", data={"username": "nobody", "password": "whatever123"})
    assert resp.status_code == 400


def test_issued_token_has_issuer_claim(client, register_user):
    username, password = register_user()
    resp = client.post("/api/login", data={"username": username, "password": password})
    token = resp.json()["access_token"]
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["iss"] == "registry-backend"
    assert payload["sub"] == username


def test_dashboard_requires_auth(client):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 401


def test_dashboard_rejects_token_from_other_service(client, register_user):
    username, _ = register_user()
    # Minted with a different secret AND a different issuer, simulating a token
    # that leaked/was reused from social-backend.
    foreign_token = jwt.encode(
        {"sub": username, "iss": "social-backend"}, "some-other-services-secret", algorithm="HS256"
    )
    resp = client.get("/api/dashboard", headers={"Authorization": f"Bearer {foreign_token}"})
    assert resp.status_code == 401


def test_dashboard_rejects_token_with_wrong_issuer_same_secret(client, register_user):
    username, _ = register_user()
    # Even if somehow signed with the right secret, a mismatched "iss" must be rejected.
    forged = jwt.encode({"sub": username, "iss": "social-backend"}, auth.SECRET_KEY, algorithm="HS256")
    resp = client.get("/api/dashboard", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


def test_dashboard_rejects_expired_token(client, register_user):
    import datetime

    username, _ = register_user()
    expired = jwt.encode(
        {"sub": username, "iss": "registry-backend", "exp": datetime.datetime.utcnow() - datetime.timedelta(minutes=5)},
        auth.SECRET_KEY,
        algorithm="HS256",
    )
    resp = client.get("/api/dashboard", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


def test_dashboard_rejects_malformed_token(client):
    resp = client.get("/api/dashboard", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_download_token_cannot_authenticate_as_session(client, auth_headers):
    """A short-lived, image-scoped download token must not work as a general session token."""
    scoped = auth.create_access_token(
        data={"sub": auth_headers["username"], "user_id": 1, "image_id": 1}, purpose="download"
    )
    resp = client.get("/api/dashboard", headers={"Authorization": f"Bearer {scoped}"})
    assert resp.status_code == 401
