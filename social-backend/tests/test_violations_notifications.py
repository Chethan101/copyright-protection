def client_login(client, username, password):
    resp = client.post("/api/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_violation_alert_reaches_the_original_owner(client, register_user, test_image_bytes, mock_registry):
    """The attacker's own /api/violations shows it under my_violations; the person whose
    content was stolen should see it under notifications, keyed by original_owner_name.

    owner_id below is deliberately a large, unrelated number rather than the owner's
    real social-backend user id: registry-backend and social-backend have entirely
    independent user tables with independent id sequences, so verification_result's
    "owner_id" is a *registry* id that must never be compared against a *social* user's
    current_user.id. Using a mismatched id here is what would have caught that bug --
    matching must happen on original_owner_name (a plain username string), the one
    field both services actually agree on.
    """
    owner_u, owner_p = register_user()
    attacker_u, attacker_p = register_user()
    attacker_token = client_login(client, attacker_u, attacker_p)
    owner_token = client_login(client, owner_u, owner_p)

    mock_registry(json_response={
        "is_registered": True,
        "owner_name": owner_u,
        "owner_id": 987654,  # unrelated registry-side id, see docstring above
        "image_id": 1,
        "tx_hash": "0xabc",
        "timestamp": "2026-01-01T00:00:00",
        "confidence": 88.0,
    })
    blocked = client.post(
        "/api/posts/upload",
        headers={"Authorization": f"Bearer {attacker_token}"},
        files={"file": ("stolen.png", test_image_bytes, "image/png")},
    )
    assert blocked.status_code == 403

    attacker_view = client.get("/api/violations", headers={"Authorization": f"Bearer {attacker_token}"}).json()
    assert len(attacker_view["my_violations"]) == 1
    assert attacker_view["notifications"] == []

    owner_view = client.get("/api/violations", headers={"Authorization": f"Bearer {owner_token}"}).json()
    assert owner_view["my_violations"] == []
    assert len(owner_view["notifications"]) == 1
    assert owner_view["notifications"][0]["original_owner_name"] == owner_u


def test_violations_requires_auth(client):
    resp = client.get("/api/violations")
    assert resp.status_code == 401
