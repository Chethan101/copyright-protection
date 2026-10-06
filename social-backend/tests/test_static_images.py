import pytest


def _upload(client, headers, image_bytes, mock_registry):
    mock_registry(json_response={"is_registered": False})
    resp = client.post(
        "/api/posts/upload",
        headers=headers,
        files={"file": ("photo.png", image_bytes, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["post_id"]


def test_serve_image_returns_uploaded_file(client, auth_headers, test_image_bytes, mock_registry):
    _upload(client, auth_headers["headers"], test_image_bytes, mock_registry)
    feed = client.get("/api/feed", headers=auth_headers["headers"]).json()["posts"]
    image_url = feed[0]["image_url"]
    assert image_url.startswith("/api/images/")

    resp = client.get(image_url)
    assert resp.status_code == 200
    assert resp.content == test_image_bytes


def test_serve_image_404_for_missing_file(client):
    resp = client.get("/api/images/does_not_exist.png")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "malicious_name",
    [
        "..%2f..%2f..%2fetc%2fpasswd",
        "..\\..\\..\\Windows\\win.ini",
        "..%5c..%5cWindows%5cwin.ini",
    ],
)
def test_serve_image_rejects_traversal_attempts(client, malicious_name):
    resp = client.get(f"/api/images/{malicious_name}")
    assert resp.status_code in (400, 404)  # never a 200 with unexpected file content
