"""
Safeguards against wrongly attributing ownership -- each one reproduces a failure that
actually happened in this project's registry.

  * An unrelated photo scored "100%" against an out-of-focus video frame on raw
    descriptor matches that did not line up geometrically. Because that video belonged
    to the uploader, someone else's registered content was waved through.
  * Unrelated screen recordings share identical UI chrome (e.g. a record button) and
    can line up genuinely -- but only over a tiny region of the picture.
  * Registration only rejected byte-identical files, so a screenshot or re-save of
    someone else's registered photo could be minted to a second owner.
  * Any exception during the scan returned "not registered", letting content through.
"""
import io

import cv2
import numpy as np
import pytest
from PIL import Image

from app import watermark_engine
from .conftest import INTERNAL_HEADERS, make_test_image_bytes

BLOCK_THRESHOLD = 50.0


# ── Scoring: geometry and coverage are both required ────────────────────────────

def _random_descriptors(rng, n):
    return rng.integers(0, 256, (n, 32), dtype=np.uint8)


def test_matching_descriptors_without_geometry_never_score():
    """
    Many descriptor matches that don't line up under any single projection are
    coincidences. Here every descriptor has an exact twin, but the twins sit at random,
    unrelated positions -- the shape of the real false block (37 matches, 9 aligned).
    """
    rng = np.random.default_rng(1)
    desc = _random_descriptors(rng, 300)
    pts_a = rng.uniform(0, 1000, (300, 2)).astype(np.float32)
    pts_b = rng.uniform(0, 1000, (300, 2)).astype(np.float32)

    score = watermark_engine.orb_similarity_from_features((pts_a, desc), (pts_b, desc.copy()))
    assert score == 0.0


def _two_images_matching_over(region_box, rng):
    """
    Two feature sets with 600 unrelated keypoints each spread over a 1000x800 frame,
    plus 150 points that match exactly and line up perfectly (a pure translation) --
    but only inside `region_box` = (x0, y0, x1, y1).
    """
    x0, y0, x1, y1 = region_box
    shared = np.column_stack([rng.uniform(x0, x1, 150), rng.uniform(y0, y1, 150)]).astype(np.float32)
    shared_desc = _random_descriptors(rng, 150)

    def frame(offset):
        bg = rng.uniform([0, 0], [1000, 800], (600, 2)).astype(np.float32)
        pts = np.vstack([bg, shared + offset]).astype(np.float32)
        desc = np.vstack([_random_descriptors(rng, 600), shared_desc])
        return pts, desc

    return frame(np.float32([0, 0])), frame(np.float32([3, 2]))


def test_identical_small_region_does_not_count_as_a_copy():
    """
    Unrelated screen recordings can share pixel-identical UI chrome. That region lines
    up perfectly, but covers a tiny share of each picture -- not a copy of the content.
    """
    rng = np.random.default_rng(2)
    a, b = _two_images_matching_over((440, 380, 520, 410), rng)   # ~80x30 "button"
    assert watermark_engine.orb_similarity_from_features(a, b) == 0.0


def test_control_same_construction_over_the_whole_picture_does_match():
    """Guards the test above against being vacuous: spread over the frame, it matches."""
    rng = np.random.default_rng(2)
    a, b = _two_images_matching_over((0, 0, 1000, 800), rng)
    assert watermark_engine.orb_similarity_from_features(a, b) > BLOCK_THRESHOLD


# ── End to end through the API ──────────────────────────────────────────────────

def _login(client, username, password):
    return client.post("/api/login", data={"username": username, "password": password}).json()["access_token"]


def _register(client, token, image_bytes, name="x.png"):
    return client.post("/api/images/register", headers={"Authorization": f"Bearer {token}"},
                       files={"file": (name, image_bytes, "image/png")})


def _watermarked(client, token, image_id):
    dl = client.post(f"/api/images/{image_id}/download-token",
                     headers={"Authorization": f"Bearer {token}"}).json()["token"]
    return client.get(f"/api/images/{image_id}/download", params={"token": dl}).content


def _screenshot(image_bytes):
    """Downscale, upscale and re-save: changes every byte while keeping the picture."""
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    shot = cv2.resize(cv2.resize(img, (int(w * 0.8), int(h * 0.8))), (w, h))
    ok, enc = cv2.imencode(".png", shot)
    return enc.tobytes()


def _crop(image_bytes, frac=0.15):
    """Trim each edge: a genuine edit that changes the perceptual hash."""
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    ok, enc = cv2.imencode(".png", img[int(h * frac):int(h * (1 - frac)), int(w * frac):int(w * (1 - frac))])
    return enc.tobytes()


def _photo_bytes(seed, size=512):
    """Detailed, photo-like content (unrelated across seeds)."""
    rng = np.random.default_rng(seed)
    img = np.full((size, size, 3), 120, dtype=np.uint8)
    for _ in range(220):
        x, y = (int(v) for v in rng.integers(0, size, 2))
        r = int(rng.integers(4, 26))
        colour = tuple(int(c) for c in rng.integers(0, 255, 3))
        if rng.random() < 0.5:
            cv2.rectangle(img, (x, y), (x + r, y + r), colour, -1)
        else:
            cv2.circle(img, (x, y), r // 2, colour, -1)
    buf = io.BytesIO()
    Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(buf, format="PNG")
    return buf.getvalue()


def test_cannot_register_a_copy_of_someone_elses_registered_content(client, register_user):
    owner_u, owner_p = register_user()
    other_u, other_p = register_user()
    owner_tok, other_tok = _login(client, owner_u, owner_p), _login(client, other_u, other_p)

    original = _register(client, owner_tok, _photo_bytes(7))
    assert original.status_code == 200
    copy = _screenshot(_watermarked(client, owner_tok, original.json()["image_id"]))

    stolen = _register(client, other_tok, copy, "mine.png")
    assert stolen.status_code == 409
    assert owner_u in stolen.json()["detail"]


def test_the_same_owner_cannot_register_the_same_content_twice(client, register_user):
    """
    One registration per picture. Two registrations of the same photo (seen in this
    registry as #92 and #93) made a block cite whichever was scanned first.
    """
    u, p = register_user()
    tok = _login(client, u, p)
    original = _register(client, tok, _photo_bytes(8))
    assert original.status_code == 200
    again = _register(client, tok, _crop(_watermarked(client, tok, original.json()["image_id"])), "again.png")
    assert again.status_code == 409
    assert "already registered" in again.json()["detail"]


def test_a_copy_cites_the_registration_it_was_made_from(client, register_user, monkeypatch):
    """
    Where the same picture already exists twice (legacy data), a copy must be attributed
    to the record it lines up with best -- not simply the oldest strong match.
    """
    import app.main as main_module
    u, p = register_user()
    tok = _login(client, u, p)
    base = _photo_bytes(55, size=640)
    first = _register(client, tok, _crop(base, 0.12), "first.png")      # same picture, cropped
    assert first.status_code == 200
    real_find = main_module._find_registered_match
    monkeypatch.setattr(main_module, "_find_registered_match", lambda *a, **k: (None, 0.0, None))
    second = _register(client, tok, base, "second.png")                  # forced legacy duplicate
    monkeypatch.setattr(main_module, "_find_registered_match", real_find)
    assert second.status_code == 200

    copy = _screenshot(_watermarked(client, tok, second.json()["image_id"]))
    # Visual evidence only, as with a re-photograph that destroyed the watermark.
    monkeypatch.setattr(watermark_engine, "extract_watermark", lambda *a, **k: "0" * 64)
    result = client.post("/api/verify-watermark", headers=INTERNAL_HEADERS,
                         files={"file": ("copy.png", copy, "image/png")}).json()
    assert result["image_id"] == second.json()["image_id"]


def test_cannot_register_a_crop_of_someone_elses_content(client, register_user):
    """A crop changes the file and its hash -- the ownership check must still see it."""
    owner_u, owner_p = register_user()
    other_u, other_p = register_user()
    original = _register(client, _login(client, owner_u, owner_p), _photo_bytes(9))
    assert original.status_code == 200
    crop = _crop(_watermarked(client, _login(client, owner_u, owner_p), original.json()["image_id"]))
    stolen = _register(client, _login(client, other_u, other_p), crop, "mine.png")
    assert stolen.status_code == 409


def test_unrelated_content_still_registers(client, register_user):
    a_u, a_p = register_user()
    b_u, b_p = register_user()
    assert _register(client, _login(client, a_u, a_p), _photo_bytes(11)).status_code == 200
    assert _register(client, _login(client, b_u, b_p), _photo_bytes(12)).status_code == 200


def test_a_copy_is_attributed_to_its_owner_not_to_the_uploaders_own_records(client, register_user):
    """
    The real failure: the uploader owned an unrelated registered item that falsely
    "matched", so a copy of someone else's work came back as the uploader's own.
    """
    uploader_u, uploader_p = register_user()
    owner_u, owner_p = register_user()
    uploader_tok, owner_tok = _login(client, uploader_u, uploader_p), _login(client, owner_u, owner_p)

    assert _register(client, uploader_tok, _photo_bytes(21)).status_code == 200   # uploader's own, older
    owned = _register(client, owner_tok, _photo_bytes(22))                      # someone else's
    assert owned.status_code == 200

    copy = _screenshot(_watermarked(client, owner_tok, owned.json()["image_id"]))
    result = client.post("/api/verify-watermark", headers=INTERNAL_HEADERS,
                         files={"file": ("copy.png", copy, "image/png")}).json()
    assert result["is_registered"] is True
    assert result["owner_name"] == owner_u


def test_unregistered_content_is_not_matched_to_anything(client, register_user):
    u, p = register_user()
    assert _register(client, _login(client, u, p), _photo_bytes(31)).status_code == 200
    result = client.post("/api/verify-watermark", headers=INTERNAL_HEADERS,
                         files={"file": ("new.png", _photo_bytes(32), "image/png")}).json()
    assert result == {"is_registered": False}


# ── Fail closed ─────────────────────────────────────────────────────────────────

def test_a_failed_check_refuses_rather_than_reporting_unregistered(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(watermark_engine, "extract_watermark", boom)

    resp = client.post("/api/verify-watermark", headers=INTERNAL_HEADERS,
                       files={"file": ("x.png", make_test_image_bytes(seed=3), "image/png")})
    assert resp.status_code == 503


def test_one_broken_record_does_not_disable_protection(client, register_user, monkeypatch):
    """A single unreadable stored file is skipped; the rest of the registry still protects."""
    u, p = register_user()
    tok = _login(client, u, p)
    first = _register(client, tok, _photo_bytes(41))
    second = _register(client, tok, _photo_bytes(42))
    assert first.status_code == second.status_code == 200
    copy = _screenshot(_watermarked(client, tok, second.json()["image_id"]))

    import app.main as main_module
    real = main_module._orb_candidate_path
    broken_id = first.json()["image_id"]

    def flaky(img):
        if img.id == broken_id:
            raise OSError("simulated unreadable file")
        return real(img)
    monkeypatch.setattr(main_module, "_orb_candidate_path", flaky)

    result = client.post("/api/verify-watermark", headers=INTERNAL_HEADERS,
                         files={"file": ("copy.png", copy, "image/png")}).json()
    assert result["is_registered"] is True
    assert result["image_id"] == second.json()["image_id"]


# ── Legacy records ──────────────────────────────────────────────────────────────

def test_records_with_an_older_64_bit_hash_are_still_protected(client, register_user, monkeypatch):
    """
    The earliest registrations stored an 8x8 (64-bit) perceptual hash. Comparing it to a
    16x16 upload hash raised, and the raise skipped the record -- ORB included -- so a
    copy whose watermark did not survive went through as "not registered".
    """
    import os
    import app.main as main_module
    from app import auth, models
    u, p = register_user()
    tok = _login(client, u, p)
    reg = _register(client, tok, _photo_bytes(61))
    assert reg.status_code == 200
    image_id = reg.json()["image_id"]

    # Rewrite the record as a legacy one: a 64-bit hash of the original.
    gen = client.app.dependency_overrides[auth.get_db]()
    db = next(gen)
    rec = db.get(models.ImageRecord, image_id)
    rec.image_hash = watermark_engine.get_perceptual_hash(
        os.path.join(main_module.ORIGINAL_DIR, rec.original_path), hash_size=8)
    assert len(rec.image_hash) == 16
    db.commit()
    gen.close()

    copy = _screenshot(_watermarked(client, tok, image_id))
    monkeypatch.setattr(watermark_engine, "extract_watermark", lambda *a, **k: "0" * 64)  # watermark lost
    result = client.post("/api/verify-watermark", headers=INTERNAL_HEADERS,
                         files={"file": ("copy.png", copy, "image/png")}).json()
    assert result["is_registered"] is True
    assert result["image_id"] == image_id


def _flat_bytes(bgr, label):
    img = np.full((200, 200, 3), bgr, dtype=np.uint8)
    cv2.putText(img, label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    ok, enc = cv2.imencode(".png", img)
    return enc.tobytes()


def test_a_plain_colour_upload_is_not_blamed_on_another_plain_colour_registration(client, register_user):
    """
    Near-uniform pictures have no usable perceptual hash: their hashes coincide by chance
    (measured: a plain green test image matched another user's plain blue one at a
    64-bit-hash distance of 2). The coincidence is reproduced exactly here -- the stored
    hash equals the upload's -- and must still not count as evidence of copying.
    """
    import os
    from PIL import Image as PILImage
    import io as _io
    from app import auth, models
    u, p = register_user()
    blue = _register(client, _login(client, u, p), _flat_bytes((190, 160, 110), "1785595354.58"))
    assert blue.status_code == 200
    green = _flat_bytes((80, 150, 110), "1785657193.77")

    gen = client.app.dependency_overrides[auth.get_db]()
    db = next(gen)
    rec = db.get(models.ImageRecord, blue.json()["image_id"])
    rec.image_hash = str(watermark_engine.imagehash.phash(PILImage.open(_io.BytesIO(green)).convert("RGB"), hash_size=8))
    db.commit()
    gen.close()

    result = client.post("/api/verify-watermark", headers=INTERNAL_HEADERS,
                         files={"file": ("green.png", green, "image/png")}).json()
    assert result == {"is_registered": False}


def test_upload_that_cannot_be_analysed_fails_closed(client, register_user, monkeypatch):
    """
    If the UPLOAD's own features cannot be computed, the scan used to skip every record
    one by one and report "not registered" -- letting a screenshot of protected work
    through. It must refuse instead.
    """
    u, p = register_user()
    assert _register(client, _login(client, u, p), _photo_bytes(71)).status_code == 200

    real = watermark_engine.compute_orb_features_multi
    def failing_for_uploads(paths):
        if any("wm_" not in os.path.basename(str(x)) for x in paths):
            raise RuntimeError("simulated: cannot decode upload")
        return real(paths)
    import os
    monkeypatch.setattr(watermark_engine, "compute_orb_features_multi", failing_for_uploads)
    monkeypatch.setattr(watermark_engine, "extract_watermark", lambda *a, **k: "0" * 64)

    resp = client.post("/api/verify-watermark", headers=INTERNAL_HEADERS,
                       files={"file": ("shot.png", _photo_bytes(72), "image/png")})
    assert resp.status_code == 503


def test_registration_leaves_no_analysis_files_beside_the_original(client, register_user):
    import os
    import app.main as main_module
    u, p = register_user()
    assert _register(client, _login(client, u, p), _photo_bytes(73)).status_code == 200
    leftovers = [f for f in os.listdir(main_module.ORIGINAL_DIR) if f.endswith(".npz") or "_orbkf" in f]
    assert leftovers == []


def test_dashboard_thumbnails_come_with_working_tokens(client, register_user):
    u, p = register_user()
    tok = _login(client, u, p)
    image_id = _register(client, tok, _photo_bytes(74)).json()["image_id"]
    images = client.get("/api/dashboard", headers={"Authorization": f"Bearer {tok}"}).json()["images"]
    preview = images[0]["preview_token"]
    assert client.get(f"/api/images/{image_id}/download", params={"token": preview}).status_code == 200
