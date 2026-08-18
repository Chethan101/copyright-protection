"""
ORB similarity must separate genuine derived copies from unrelated photographs.

Regression origin: the homography branch used to score any pair reaching 8 RANSAC
inliers as `max(75.0, ...)`, i.e. an automatic 75+ "confidence". Unrelated images
routinely produce a handful of chance inliers, so uploading an unregistered photo
could be blocked and misattributed to a stranger's registered content.
"""
import cv2
import numpy as np
import pytest

from app import watermark_engine as we

BLOCK_THRESHOLD = 50.0  # verify_watermark only reports a match above this


def _photo(width=640, height=480, seed=0):
    """Photo-like image: smooth gradient background plus distinct solid shapes."""
    rng = np.random.default_rng(seed)
    arr = np.zeros((height, width, 3), dtype=np.float32)
    for y in range(height):
        t = y / height
        arr[y, :, 0] = 40 + 120 * t
        arr[y, :, 1] = 80 + 100 * (1 - t * 0.3)
        arr[y, :, 2] = 150 + 80 * (1 - t)
    for _ in range(18):
        x0 = int(rng.integers(0, width))
        y0 = int(rng.integers(height // 2, height))
        bw = int(rng.integers(20, 90))
        bh = int(rng.integers(50, 220))
        arr[y0:min(height, y0 + bh), x0:min(width, x0 + bw)] = rng.integers(20, 90, size=3)
    arr += rng.normal(0, 8, (height, width, 3))
    return np.clip(arr, 0, 255).astype(np.uint8)


def _write(tmp_path, name, img):
    p = tmp_path / name
    cv2.imwrite(str(p), img)
    return str(p)


def _as_screenshot(img):
    h, w = img.shape[:2]
    small = cv2.resize(img, (int(w * 0.6), int(h * 0.6)), interpolation=cv2.INTER_AREA)
    up = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    _, enc = cv2.imencode(".jpg", up, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return cv2.imdecode(enc, cv2.IMREAD_COLOR)


def _as_camera_recapture(img, seed=7):
    """Perspective tilt + uneven lighting + optical blur + sensor noise + heavy JPEG."""
    h, w = img.shape[:2]
    rng = np.random.default_rng(seed)
    margin = 0.04
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([
        [rng.uniform(0, margin * w), rng.uniform(0, margin * h)],
        [w - rng.uniform(0, margin * w), rng.uniform(0, margin * h)],
        [w - rng.uniform(0, margin * w), h - rng.uniform(0, margin * h)],
        [rng.uniform(0, margin * w), h - rng.uniform(0, margin * h)],
    ])
    warped = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h),
                                 borderMode=cv2.BORDER_REPLICATE)
    yy, xx = np.mgrid[0:h, 0:w]
    gradient = 1.0 + 0.25 * np.sin(xx / w * np.pi) * np.cos(yy / h * np.pi)
    lit = np.clip(warped.astype(np.float32) * gradient[..., None], 0, 255).astype(np.uint8)
    blurred = cv2.GaussianBlur(lit, (3, 3), 0.6)
    noisy = np.clip(blurred.astype(np.float32) + rng.normal(0, 6, blurred.shape), 0, 255).astype(np.uint8)
    _, enc = cv2.imencode(".jpg", noisy, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return cv2.imdecode(enc, cv2.IMREAD_COLOR)


def test_identical_image_scores_maximum(tmp_path):
    img = _photo(seed=1)
    p = _write(tmp_path, "a.png", img)
    assert we.calculate_orb_similarity(p, p) > 95.0


@pytest.mark.parametrize("variant_name,transform", [
    ("screenshot", _as_screenshot),
    ("camera_recapture", _as_camera_recapture),
    ("crop", lambda im: im[int(im.shape[0] * 0.08):int(im.shape[0] * 0.92),
                           int(im.shape[1] * 0.08):int(im.shape[1] * 0.92)]),
])
def test_genuine_derived_copies_are_detected(tmp_path, variant_name, transform):
    """Screenshots, re-photographs and crops of the same content must still be caught."""
    original = _photo(seed=2)
    orig_path = _write(tmp_path, "original.png", original)
    variant_path = _write(tmp_path, f"{variant_name}.png", transform(original))

    score = we.calculate_orb_similarity(variant_path, orig_path)
    assert score > BLOCK_THRESHOLD, f"{variant_name} scored only {score}"


@pytest.mark.parametrize("seed_a,seed_b", [(11, 22), (33, 44), (55, 66), (77, 88)])
def test_unrelated_photos_do_not_false_positive(tmp_path, seed_a, seed_b):
    """Two unrelated photos must never reach the block threshold."""
    a = _write(tmp_path, f"a{seed_a}.png", _photo(seed=seed_a))
    b = _write(tmp_path, f"b{seed_b}.png", _photo(seed=seed_b))

    score = we.calculate_orb_similarity(a, b)
    assert score <= BLOCK_THRESHOLD, f"unrelated images falsely matched at {score}"


def test_chance_inliers_do_not_produce_a_confident_score(tmp_path):
    """
    Guards the specific regression: a small number of RANSAC inliers must not be
    promoted to a high confidence by a hard-coded floor. Structured images share
    incidental corner features, which previously satisfied the 8-inlier gate.
    """
    rng = np.random.default_rng(5)
    grid_a = np.full((480, 640, 3), 220, dtype=np.uint8)
    grid_b = np.full((480, 640, 3), 220, dtype=np.uint8)
    for i in range(0, 640, 40):
        grid_a[:, i:i + 3] = 30
    for i in range(0, 480, 40):
        grid_b[i:i + 3, :] = 30
    grid_a = np.clip(grid_a + rng.normal(0, 5, grid_a.shape), 0, 255).astype(np.uint8)
    grid_b = np.clip(grid_b + rng.normal(0, 5, grid_b.shape), 0, 255).astype(np.uint8)

    a = _write(tmp_path, "grid_a.png", grid_a)
    b = _write(tmp_path, "grid_b.png", grid_b)

    assert we.calculate_orb_similarity(a, b) <= BLOCK_THRESHOLD


def test_score_is_bounded(tmp_path):
    a = _write(tmp_path, "x.png", _photo(seed=3))
    b = _write(tmp_path, "y.png", _photo(seed=4))
    for score in (we.calculate_orb_similarity(a, a), we.calculate_orb_similarity(a, b)):
        assert 0.0 <= score <= 100.0


def test_low_keypoint_image_does_not_inflate_match_ratio(tmp_path):
    """
    Guards a second regression, found via a real out-of-focus video frame: the
    match-ratio score (good_matches / min(kp1, kp2) * 4) divides by the SMALLER of the
    two keypoint counts. A blurry/low-texture image has very few keypoints, so a
    handful of coincidental matches becomes a large fraction of that small denominator
    and inflates the ratio -- even against completely unrelated content. Measured: 17
    matches out of 90 keypoints scored 75.6 (above the 50 block threshold) against
    unrelated footage, while confirmed genuine matches on the same clip had 500+
    matches. Reproduced here with a heavily blurred, low-texture photo standing in for
    the out-of-focus frame.
    """
    sharp = _photo(seed=42)
    blurry = cv2.GaussianBlur(_photo(seed=99), (31, 31), 15)

    a = _write(tmp_path, "sharp.png", sharp)
    b = _write(tmp_path, "blurry.png", blurry)

    features_b = we.compute_orb_features(b)
    if features_b is not None:
        assert len(features_b[0]) < 150, "test fixture must itself be low-texture to exercise this path"

    score = we.calculate_orb_similarity(a, b)
    assert score <= BLOCK_THRESHOLD, f"low-keypoint image falsely matched at {score}"
