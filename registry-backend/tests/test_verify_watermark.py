from .conftest import INTERNAL_HEADERS


def test_verify_watermark_requires_internal_key(client, test_image_bytes):
    resp = client.post("/api/verify-watermark", files={"file": ("x.png", test_image_bytes, "image/png")})
    assert resp.status_code == 403


def test_verify_watermark_rejects_wrong_internal_key(client, test_image_bytes):
    resp = client.post(
        "/api/verify-watermark",
        headers={"x-registry-internal": "totally-wrong-key"},
        files={"file": ("x.png", test_image_bytes, "image/png")},
    )
    assert resp.status_code == 403


def test_verify_watermark_true_negative_for_unrelated_image(client, registered_image, other_image_bytes):
    resp = client.post(
        "/api/verify-watermark",
        headers=INTERNAL_HEADERS,
        files={"file": ("unrelated.png", other_image_bytes, "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["is_registered"] is False


def test_verify_watermark_true_positive_via_phash_on_resubmitted_original(client, registered_image, test_image_bytes):
    # Resubmitting the exact bytes that were registered must phash-match itself (distance 0).
    resp = client.post(
        "/api/verify-watermark",
        headers=INTERNAL_HEADERS,
        files={"file": ("photo.png", test_image_bytes, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_registered"] is True
    assert body["image_id"] == registered_image["image_id"]
    assert body["confidence"] > 50.0
    # No Ganache in the test environment -> must fail closed, not silently claim "verified".
    assert body["blockchain_verified"] is False


def test_verify_watermark_true_positive_via_exact_watermark_match_on_downloaded_copy(client, auth_headers, registered_image):
    token_resp = client.post(
        f"/api/images/{registered_image['image_id']}/download-token",
        headers=auth_headers["headers"],
    )
    assert token_resp.status_code == 200
    dl_token = token_resp.json()["token"]

    dl_resp = client.get(f"/api/images/{registered_image['image_id']}/download?token={dl_token}")
    assert dl_resp.status_code == 200
    watermarked_bytes = dl_resp.content

    resp = client.post(
        "/api/verify-watermark",
        headers=INTERNAL_HEADERS,
        files={"file": ("downloaded.png", watermarked_bytes, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_registered"] is True
    assert body["watermark_id"] == registered_image["watermark_id"]
    assert body["confidence"] >= 99.0  # exact watermark_id match tier
