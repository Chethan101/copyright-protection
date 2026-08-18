def test_dashboard_shows_only_own_images(client, register_user, test_image_bytes, other_image_bytes):
    u1, p1 = register_user()
    u2, p2 = register_user()
    t1 = client.post("/api/login", data={"username": u1, "password": p1}).json()["access_token"]
    t2 = client.post("/api/login", data={"username": u2, "password": p2}).json()["access_token"]

    client.post(
        "/api/images/register",
        headers={"Authorization": f"Bearer {t1}"},
        files={"file": ("a.png", test_image_bytes, "image/png")},
    )
    client.post(
        "/api/images/register",
        headers={"Authorization": f"Bearer {t2}"},
        files={"file": ("b.png", other_image_bytes, "image/png")},
    )

    dash1 = client.get("/api/dashboard", headers={"Authorization": f"Bearer {t1}"}).json()
    assert dash1["stats"]["my_images"] == 1
    assert dash1["stats"]["total_network_images"] == 2


def test_download_token_requires_ownership(client, register_user, registered_image, test_image_bytes):
    other_username, other_password = register_user()
    other_token = client.post(
        "/api/login", data={"username": other_username, "password": other_password}
    ).json()["access_token"]

    resp = client.post(
        f"/api/images/{registered_image['image_id']}/download-token",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_download_with_valid_token_succeeds(client, auth_headers, registered_image):
    token_resp = client.post(
        f"/api/images/{registered_image['image_id']}/download-token",
        headers=auth_headers["headers"],
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["token"]

    dl = client.get(f"/api/images/{registered_image['image_id']}/download?token={token}")
    assert dl.status_code == 200
    assert len(dl.content) > 0


def test_download_rejects_token_scoped_to_a_different_image(client, auth_headers, registered_image):
    token_resp = client.post(
        f"/api/images/{registered_image['image_id']}/download-token",
        headers=auth_headers["headers"],
    )
    token = token_resp.json()["token"]
    other_image_id = registered_image["image_id"] + 999
    dl = client.get(f"/api/images/{other_image_id}/download?token={token}")
    assert dl.status_code == 401


def test_download_rejects_garbage_token(client, registered_image):
    dl = client.get(f"/api/images/{registered_image['image_id']}/download?token=not-a-real-token")
    assert dl.status_code == 401


