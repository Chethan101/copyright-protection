"""
An exact watermark match must decide ownership, ahead of any visual similarity.

Regression origin: the scan visited records oldest-first and stopped on the first
visual match of 97%+. An older registration that merely *looked* similar could end
the scan before a newer record whose watermark matched exactly was reached, so a
block cited the wrong registration -- its watermark id, transaction and block.
"""
from app import watermark_engine
from .conftest import INTERNAL_HEADERS


def _token(client, username, password):
    return client.post("/api/login", data={"username": username, "password": password}).json()["access_token"]


def _register(client, token, image_bytes, name):
    resp = client.post(
        "/api/images/register",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (name, image_bytes, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _watermarked_copy(client, token, image_id):
    dl_token = client.post(
        f"/api/images/{image_id}/download-token", headers={"Authorization": f"Bearer {token}"}
    ).json()["token"]
    return client.get(f"/api/images/{image_id}/download", params={"token": dl_token}).content


def _perfect_visual_match(*a, **k):
    """Every record lines up perfectly -- the strongest visual evidence possible."""
    return 100.0, 10_000


def test_exact_watermark_beats_an_older_visual_match(
        client, register_user, test_image_bytes, other_image_bytes, monkeypatch):
    older_user, older_pw = register_user()
    newer_user, newer_pw = register_user()
    older_tok = _token(client, older_user, older_pw)
    newer_tok = _token(client, newer_user, newer_pw)

    older = _register(client, older_tok, other_image_bytes, "older.png")
    newer = _register(client, newer_tok, test_image_bytes, "newer.png")
    upload = _watermarked_copy(client, newer_tok, newer["image_id"])

    # Simulate the failure: every record looks like a perfect visual match, so the
    # older record would win if visual matching ran before the exact watermark check.
    monkeypatch.setattr(watermark_engine, "best_orb_match", _perfect_visual_match)

    result = client.post(
        "/api/verify-watermark",
        headers=INTERNAL_HEADERS,
        files={"file": ("upload.png", upload, "image/png")},
    ).json()

    assert result["is_registered"] is True
    assert result["match_method"] == "watermark"
    assert result["image_id"] == newer["image_id"], (
        f"attributed to older record {older['image_id']} instead of the exact watermark match"
    )
    assert result["owner_name"] == newer_user
    assert result["watermark_id"] == newer["watermark_id"]


def test_control_the_simulated_visual_match_is_actually_used(
        client, register_user, test_image_bytes, other_image_bytes, monkeypatch):
    """
    Guards the test above against being vacuous (it once patched a function the scan no
    longer called): with the watermark unreadable, the simulated visual match must decide.
    """
    older_user, older_pw = register_user()
    newer_user, newer_pw = register_user()
    older = _register(client, _token(client, older_user, older_pw), other_image_bytes, "older.png")
    newer_tok = _token(client, newer_user, newer_pw)
    newer = _register(client, newer_tok, test_image_bytes, "newer.png")
    upload = _watermarked_copy(client, newer_tok, newer["image_id"])

    monkeypatch.setattr(watermark_engine, "best_orb_match", _perfect_visual_match)
    monkeypatch.setattr(watermark_engine, "extract_watermark", lambda *a, **k: "0" * 64)

    result = client.post("/api/verify-watermark", headers=INTERNAL_HEADERS,
                         files={"file": ("upload.png", upload, "image/png")}).json()
    assert result["match_method"] == "orb_visual_similarity"
    assert result["image_id"] == older["image_id"]   # tie goes to the first record scanned
