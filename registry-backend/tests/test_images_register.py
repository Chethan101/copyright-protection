import os

import app.main as main_module
from .conftest import make_test_image_bytes


def test_register_image_requires_auth(client, test_image_bytes):
    resp = client.post("/api/images/register", files={"file": ("photo.png", test_image_bytes, "image/png")})
    assert resp.status_code == 401


def test_register_image_success(client, auth_headers, test_image_bytes):
    resp = client.post(
        "/api/images/register",
        headers=auth_headers["headers"],
        files={"file": ("photo.png", test_image_bytes, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["watermark_id"]
    assert body["image_hash"]
    assert body["tx_hash"]
    assert "blockchain_registered" in body
    # No Ganache running in the test environment -> falls back to DB-only registration honestly.
    assert body["blockchain_registered"] is False
    assert "blockchain notarization unavailable" in body["msg"]


def test_register_image_persists_files_with_server_generated_names(client, auth_headers, test_image_bytes):
    resp = client.post(
        "/api/images/register",
        headers=auth_headers["headers"],
        files={"file": ("../../evil name with spaces.png", test_image_bytes, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    # Original client filename must never leak into the on-disk path.
    for name in os.listdir(main_module.ORIGINAL_DIR):
        assert ".." not in name
        assert "evil" not in name
    for name in os.listdir(main_module.WATERMARKED_DIR):
        assert ".." not in name
        assert "evil" not in name


def test_register_duplicate_image_rejected(client, auth_headers, test_image_bytes):
    first = client.post(
        "/api/images/register",
        headers=auth_headers["headers"],
        files={"file": ("photo.png", test_image_bytes, "image/png")},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/images/register",
        headers=auth_headers["headers"],
        files={"file": ("photo_again.png", test_image_bytes, "image/png")},
    )
    assert second.status_code == 400


def test_register_rejects_disallowed_extension(client, auth_headers):
    resp = client.post(
        "/api/images/register",
        headers=auth_headers["headers"],
        files={"file": ("payload.exe", b"not really an executable, just bytes", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_register_rejects_corrupt_file_and_leaves_no_orphan(client, auth_headers):
    before = set(os.listdir(main_module.ORIGINAL_DIR))
    resp = client.post(
        "/api/images/register",
        headers=auth_headers["headers"],
        files={"file": ("broken.png", b"this is not a valid png file at all", "image/png")},
    )
    assert resp.status_code == 400
    after = set(os.listdir(main_module.ORIGINAL_DIR))
    assert before == after  # nothing orphaned on disk


def test_register_rejects_empty_file(client, auth_headers):
    resp = client.post(
        "/api/images/register",
        headers=auth_headers["headers"],
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp.status_code == 400


def test_register_oversized_file_rejected(client, auth_headers, monkeypatch):
    import app.config as config

    monkeypatch.setattr(config, "MAX_UPLOAD_SIZE_BYTES", 100)
    big = make_test_image_bytes(width=256, height=256, seed=7)
    assert len(big) > 100
    resp = client.post(
        "/api/images/register",
        headers=auth_headers["headers"],
        files={"file": ("big.png", big, "image/png")},
    )
    assert resp.status_code == 413


def test_two_users_registering_the_same_content_second_gets_clean_400_not_500(client, register_user, test_image_bytes):
    u1, p1 = register_user()
    u2, p2 = register_user()
    t1 = client.post("/api/login", data={"username": u1, "password": p1}).json()["access_token"]
    t2 = client.post("/api/login", data={"username": u2, "password": p2}).json()["access_token"]

    r1 = client.post(
        "/api/images/register",
        headers={"Authorization": f"Bearer {t1}"},
        files={"file": ("a.png", test_image_bytes, "image/png")},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/images/register",
        headers={"Authorization": f"Bearer {t2}"},
        files={"file": ("b.png", test_image_bytes, "image/png")},
    )
    assert r2.status_code == 400  # not an unhandled 500
