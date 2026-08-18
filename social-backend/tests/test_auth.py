import jwt

from app import auth


def test_register_success(client):
    resp = client.post("/api/register", data={"username": "alice", "password": "strongpass123"})
    assert resp.status_code == 200


def test_register_duplicate_username_rejected(client):
    client.post("/api/register", data={"username": "alice", "password": "strongpass123"})
    resp = client.post("/api/register", data={"username": "alice", "password": "other12345"})
    assert resp.status_code == 400


def test_register_short_password_rejected(client):
    resp = client.post("/api/register", data={"username": "bob", "password": "short"})
    assert resp.status_code == 400


def test_login_success(client, register_user):
    username, password = register_user()
    resp = client.post("/api/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password_rejected(client, register_user):
    username, _ = register_user()
    resp = client.post("/api/login", data={"username": username, "password": "wrong-password"})
    assert resp.status_code == 400


def test_issued_token_has_issuer_claim(client, register_user):
    username, password = register_user()
    token = client.post("/api/login", data={"username": username, "password": password}).json()["access_token"]
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["iss"] == "social-backend"


def test_feed_requires_auth(client):
    resp = client.get("/api/feed")
    assert resp.status_code == 401


def test_feed_rejects_token_from_other_service(client, register_user):
    username, _ = register_user()
    foreign_token = jwt.encode(
        {"sub": username, "iss": "registry-backend"}, "some-other-services-secret", algorithm="HS256"
    )
    resp = client.get("/api/feed", headers={"Authorization": f"Bearer {foreign_token}"})
    assert resp.status_code == 401


def test_feed_rejects_token_signed_with_registry_secret_even_if_leaked(client, register_user):
    """Regression guard for the original cross-service token confusion bug: a token that
    is somehow signed with what used to be the shared secret must still be rejected here
    because the issuer claim now identifies which service minted it."""
    username, _ = register_user()
    forged = jwt.encode({"sub": username, "iss": "registry-backend"}, auth.SECRET_KEY, algorithm="HS256")
    resp = client.get("/api/feed", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401
