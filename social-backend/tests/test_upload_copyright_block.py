import requests


def test_upload_succeeds_when_content_is_unregistered(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    resp = client.post(
        "/api/posts/upload",
        headers=auth_headers["headers"],
        files={"file": ("photo.png", test_image_bytes, "image/png")},
        data={"caption": "hello world"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["post_id"]


def test_upload_succeeds_when_content_belongs_to_the_uploader_themself(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": True, "owner_name": auth_headers["username"]})
    resp = client.post(
        "/api/posts/upload",
        headers=auth_headers["headers"],
        files={"file": ("photo.png", test_image_bytes, "image/png")},
    )
    assert resp.status_code == 200, resp.text


def test_upload_blocked_when_content_belongs_to_someone_else(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={
        "is_registered": True,
        "owner_name": "someone_else",
        "owner_id": 42,
        "image_id": 7,
        "tx_hash": "0xdeadbeef",
        "timestamp": "2026-01-01T00:00:00",
        "confidence": 97.5,
    })
    resp = client.post(
        "/api/posts/upload",
        headers=auth_headers["headers"],
        files={"file": ("stolen.png", b"fake-bytes-content-doesnt-matter-since-registry-is-mocked", "image/png")},
    )
    assert resp.status_code == 403
    body = resp.json()["detail"]
    assert body["owner_name"] == "someone_else"
    assert body["confidence"] == 97.5


def test_upload_blocked_attempt_writes_violation_log(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={
        "is_registered": True,
        "owner_name": "someone_else",
        "owner_id": 42,
        "image_id": 7,
        "tx_hash": "0xdeadbeef",
        "timestamp": "2026-01-01T00:00:00",
        "confidence": 97.5,
    })
    client.post(
        "/api/posts/upload",
        headers=auth_headers["headers"],
        files={"file": ("stolen.png", test_image_bytes, "image/png")},
    )
    resp = client.get("/api/violations", headers=auth_headers["headers"])
    assert resp.status_code == 200
    violations = resp.json()["my_violations"]
    assert len(violations) == 1
    assert violations[0]["original_owner_name"] == "someone_else"
    assert violations[0]["reason"] == "Unauthorized Upload Attempt"


def test_upload_no_post_created_when_blocked(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": True, "owner_name": "someone_else", "owner_id": 42})
    client.post(
        "/api/posts/upload",
        headers=auth_headers["headers"],
        files={"file": ("stolen.png", test_image_bytes, "image/png")},
    )
    feed = client.get("/api/feed", headers=auth_headers["headers"]).json()["posts"]
    assert feed == []


def test_upload_registry_unreachable_returns_clean_500_not_stack_trace(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(exception=requests.exceptions.ConnectionError("registry is down"))
    resp = client.post(
        "/api/posts/upload",
        headers=auth_headers["headers"],
        files={"file": ("photo.png", test_image_bytes, "image/png")},
    )
    assert resp.status_code == 500
    assert "Registry check failed" in resp.json()["detail"]


def test_upload_sends_internal_api_key_header_to_registry(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    client.post(
        "/api/posts/upload",
        headers=auth_headers["headers"],
        files={"file": ("photo.png", test_image_bytes, "image/png")},
    )
    assert len(mock_registry.calls) == 1
    sent_headers = mock_registry.calls[0]["kwargs"].get("headers", {})
    assert sent_headers.get("x-registry-internal") == "test-internal-key"


def test_upload_rejects_disallowed_extension(client, auth_headers, mock_registry):
    resp = client.post(
        "/api/posts/upload",
        headers=auth_headers["headers"],
        files={"file": ("payload.exe", b"not an image", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert len(mock_registry.calls) == 0  # never even reached the registry check


def test_upload_requires_auth(client, test_image_bytes):
    resp = client.post("/api/posts/upload", files={"file": ("photo.png", test_image_bytes, "image/png")})
    assert resp.status_code == 401


def test_upload_persists_with_server_generated_filename(client, auth_headers, test_image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    resp = client.post(
        "/api/posts/upload",
        headers=auth_headers["headers"],
        files={"file": ("../../evil name.png", test_image_bytes, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    feed = client.get("/api/feed", headers=auth_headers["headers"]).json()["posts"]
    assert "evil" not in feed[0]["image_url"]
    assert ".." not in feed[0]["image_url"]
