def _upload(client, headers, image_bytes, caption="", filename="photo.png"):
    resp = client.post(
        "/api/posts/upload",
        headers=headers,
        files={"file": (filename, image_bytes, "image/png")},
        data={"caption": caption},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["post_id"]


def test_feed_orders_newest_first(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    first_id = _upload(client, auth_headers["headers"], test_image_bytes, caption="first")
    second_id = _upload(client, auth_headers["headers"], test_image_bytes, caption="second")
    feed = client.get("/api/feed", headers=auth_headers["headers"]).json()["posts"]
    assert [p["id"] for p in feed[:2]] == [second_id, first_id]


def test_profile_returns_users_posts(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    _upload(client, auth_headers["headers"], test_image_bytes)
    resp = client.get(f"/api/profile/{auth_headers['username']}", headers=auth_headers["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["posts_count"] == 1
    assert body["user"]["username"] == auth_headers["username"]


def test_profile_unknown_user_404(client, auth_headers):
    resp = client.get("/api/profile/no-such-user", headers=auth_headers["headers"])
    assert resp.status_code == 404


def test_like_toggle(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    post_id = _upload(client, auth_headers["headers"], test_image_bytes)

    like_resp = client.post(f"/api/posts/{post_id}/like", headers=auth_headers["headers"])
    assert like_resp.status_code == 200
    assert like_resp.json() == {"liked": True, "likes_count": 1}

    unlike_resp = client.post(f"/api/posts/{post_id}/like", headers=auth_headers["headers"])
    assert unlike_resp.json() == {"liked": False, "likes_count": 0}


def test_like_nonexistent_post_404(client, auth_headers):
    resp = client.post("/api/posts/99999/like", headers=auth_headers["headers"])
    assert resp.status_code == 404


def test_comment_add_and_reject_empty(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    post_id = _upload(client, auth_headers["headers"], test_image_bytes)

    ok = client.post(f"/api/posts/{post_id}/comment", headers=auth_headers["headers"], json={"text": "nice!"})
    assert ok.status_code == 200
    assert ok.json()["text"] == "nice!"

    empty = client.post(f"/api/posts/{post_id}/comment", headers=auth_headers["headers"], json={"text": "   "})
    assert empty.status_code == 400


def test_comment_delete_requires_ownership(client, register_user, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    owner_u, owner_p = register_user()
    other_u, other_p = register_user()
    owner_token = client_login(client, owner_u, owner_p)
    other_token = client_login(client, other_u, other_p)

    post_id = _upload(client, {"Authorization": f"Bearer {owner_token}"}, test_image_bytes)
    comment_resp = client.post(
        f"/api/posts/{post_id}/comment",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"text": "my own comment"},
    )
    comment_id = comment_resp.json()["id"]

    forbidden = client.delete(
        f"/api/comments/{comment_id}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert forbidden.status_code == 403

    allowed = client.delete(
        f"/api/comments/{comment_id}", headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert allowed.status_code == 200


def client_login(client, username, password):
    resp = client.post("/api/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_repost_success_and_duplicate_rejected(client, register_user, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    owner_u, owner_p = register_user()
    reposter_u, reposter_p = register_user()
    owner_token = client_login(client, owner_u, owner_p)
    reposter_token = client_login(client, reposter_u, reposter_p)

    post_id = _upload(client, {"Authorization": f"Bearer {owner_token}"}, test_image_bytes)

    first = client.post(f"/api/posts/{post_id}/repost", headers={"Authorization": f"Bearer {reposter_token}"})
    assert first.status_code == 200

    second = client.post(f"/api/posts/{post_id}/repost", headers={"Authorization": f"Bearer {reposter_token}"})
    assert second.status_code == 400
