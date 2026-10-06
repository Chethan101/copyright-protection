"""
Brokered sign-in: VibeSocial obtains a registry session for its already-authenticated
user, so a creator has one account rather than two with matching-by-hand usernames.
"""
from .conftest import INTERNAL_HEADERS


def _session(client, username, headers=INTERNAL_HEADERS):
    return client.post("/api/internal/session", data={"username": username}, headers=headers)


def test_requires_internal_key(client):
    assert client.post("/api/internal/session", data={"username": "alice"}).status_code == 403


def test_rejects_wrong_internal_key(client):
    resp = _session(client, "alice", headers={"x-registry-internal": "wrong-key"})
    assert resp.status_code == 403


def test_provisions_user_under_the_exact_username(client):
    resp = _session(client, "alice_creator")
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice_creator"

    # The token is a normal registry session for that same user.
    dash = client.get("/api/dashboard", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert dash.status_code == 200
    assert dash.json()["user"]["username"] == "alice_creator"


def test_is_idempotent_for_an_existing_user(client):
    first = _session(client, "bob").json()
    second = _session(client, "bob").json()
    assert first["user_id"] == second["user_id"]


def test_never_hands_over_an_account_created_through_registry_signup(client, register_user, test_image_bytes):
    """
    Account takeover: anyone could sign up "victim" on the registry with a password they
    know; when the real VibeSocial user "victim" opened the Registry tab, the broker reused
    that account and the victim's registrations landed where the attacker could log in.
    """
    username, password = register_user()              # created via public signup
    resp = _session(client, username)
    assert resp.status_code == 409

    # And the attacker's account received nothing.
    tok = client.post("/api/login", data={"username": username, "password": password}).json()["access_token"]
    assert client.get("/api/dashboard", headers={"Authorization": f"Bearer {tok}"}).json()["images"] == []


def test_public_signup_cannot_claim_a_brokered_username(client):
    _session(client, "carol")
    resp = client.post("/api/register", data={"username": "carol", "password": "longenough123"})
    assert resp.status_code == 400


def test_provisioned_account_cannot_be_logged_into_with_a_password(client):
    """
    The brokered account has no usable password -- it must not be reachable through
    /api/login with anything, including an empty or guessed password.
    """
    _session(client, "carol")
    for guess in ("", "password", "carol", "testpassword123"):
        resp = client.post("/api/login", data={"username": "carol", "password": guess})
        # 400 for a wrong password, 422 when form validation rejects an empty one --
        # either way no session may be issued.
        assert resp.status_code != 200, f"logged in with guess {guess!r}"
        assert "access_token" not in resp.text


def test_rejects_blank_username(client):
    assert _session(client, "   ").status_code == 400


def test_assets_registered_via_brokered_session_are_owned_by_that_username(client, test_image_bytes):
    """
    This is the property the whole change exists for: copyright ownership is attributed
    by username, so registering through the brokered session must record the VibeSocial
    username as the owner -- which is what lets a creator post their own work.
    """
    token = _session(client, "dave_artist").json()["access_token"]
    reg = client.post(
        "/api/images/register",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("art.png", test_image_bytes, "image/png")},
    )
    assert reg.status_code == 200

    check = client.post(
        "/api/verify-watermark",
        headers=INTERNAL_HEADERS,
        files={"file": ("art.png", test_image_bytes, "image/png")},
    )
    assert check.json()["owner_name"] == "dave_artist"
