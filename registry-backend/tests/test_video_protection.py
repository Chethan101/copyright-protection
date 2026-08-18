"""
Video protection must hold up under the same attacks as stills.

Regression origin: video watermarking was effectively inert. Two independent faults
stacked up -- extraction sampled only ~1 frame per second (so a couple of degraded
frames could flip bits outright), and embedding reused the still-image alpha even
though an uploaded clip is already lossily compressed before embedding and is
re-encoded on write. An exact re-upload of a watermarked video failed to match.
"""
import os

import cv2
import numpy as np
import pytest

from app import watermark_engine as we

BLOCK_THRESHOLD = 50.0
PHASH_THRESHOLD = 8
WATERMARK_BITS = 8 * 8


def _scene(width, height, seed=0, motion_x=None):
    rng = np.random.default_rng(seed)
    base = np.zeros((height, width, 3), dtype=np.float32)
    for y in range(height):
        t = y / height
        base[y, :, 0] = 40 + 120 * t
        base[y, :, 1] = 80 + 100 * (1 - t * 0.3)
        base[y, :, 2] = 150 + 80 * (1 - t)
    for _ in range(14):
        x0 = int(rng.integers(0, width))
        y0 = int(rng.integers(height // 2, height))
        bw = int(rng.integers(30, 100))
        bh = int(rng.integers(60, 200))
        base[y0:min(height, y0 + bh), x0:min(width, x0 + bw)] = rng.integers(20, 90, size=3)
    frame = np.clip(base + rng.normal(0, 6, base.shape), 0, 255).astype(np.uint8)
    if motion_x is not None:
        cv2.circle(frame, (motion_x, height // 3), 34, (250, 250, 250), -1)
    return frame


def _write_video(path, width=640, height=480, frames=45, fps=15, seed=0):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        return None
    for i in range(frames):
        motion_x = int(60 + (width - 160) * (i / max(1, frames - 1)))
        writer.write(_scene(width, height, seed=seed, motion_x=motion_x))
    writer.release()
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    return str(path)


@pytest.fixture
def registered_video(tmp_path):
    """A source clip plus its watermarked derivative, mirroring registration."""
    src = _write_video(tmp_path / "source.mp4", seed=42)
    if src is None:
        pytest.skip("mp4v codec unavailable in this environment")
    watermark_id = "v1d30abc"
    out = str(tmp_path / "watermarked.mp4")
    we.embed_video_watermark(src, we.str_to_binary(watermark_id), out)
    return {"source": src, "watermarked": out, "watermark_id": watermark_id}


def _reencode(src, dst, scale=1.0):
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    nw, nh = max(2, int(w * scale)) // 2 * 2, max(2, int(h * scale)) // 2 * 2
    writer = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), fps, (nw, nh))
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        writer.write(cv2.resize(frame, (nw, nh)))
    cap.release(); writer.release()
    return dst


def _trim(src, dst, skip=20):
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx >= skip:
            writer.write(frame)
        idx += 1
    cap.release(); writer.release()
    return dst


def _camera_recapture(src, dst, seed=7):
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    rng = np.random.default_rng(seed)
    margin = 0.04
    src_pts = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst_pts = np.float32([
        [rng.uniform(0, margin * w), rng.uniform(0, margin * h)],
        [w - rng.uniform(0, margin * w), rng.uniform(0, margin * h)],
        [w - rng.uniform(0, margin * w), h - rng.uniform(0, margin * h)],
        [rng.uniform(0, margin * w), h - rng.uniform(0, margin * h)],
    ])
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    yy, xx = np.mgrid[0:h, 0:w]
    gradient = 1.0 + 0.25 * np.sin(xx / w * np.pi) * np.cos(yy / h * np.pi)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        warped = cv2.warpPerspective(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        lit = np.clip(warped.astype(np.float32) * gradient[..., None], 0, 255).astype(np.uint8)
        blurred = cv2.GaussianBlur(lit, (3, 3), 0.6)
        noisy = np.clip(blurred.astype(np.float32) + rng.normal(0, 6, blurred.shape), 0, 255).astype(np.uint8)
        writer.write(noisy)
    cap.release(); writer.release()
    return dst


def _extracted_id(path):
    return we.binary_to_str(we.extract_video_watermark(path, WATERMARK_BITS))


def test_exact_reupload_recovers_watermark(registered_video):
    """The baseline that was broken: re-uploading the watermarked file itself."""
    assert _extracted_id(registered_video["watermarked"]) == registered_video["watermark_id"]


def test_reencoded_video_recovers_watermark(registered_video, tmp_path):
    """Re-encoding (what any platform does on upload) must not destroy the watermark."""
    dst = _reencode(registered_video["watermarked"], str(tmp_path / "reenc.mp4"))
    assert _extracted_id(dst) == registered_video["watermark_id"]


def test_trimmed_video_recovers_watermark(registered_video, tmp_path):
    """Dropping the opening frames must not defeat extraction."""
    dst = _trim(registered_video["watermarked"], str(tmp_path / "trim.mp4"), skip=20)
    assert _extracted_id(dst) == registered_video["watermark_id"]


def test_unrelated_video_does_not_yield_the_watermark(registered_video, tmp_path):
    other = _write_video(tmp_path / "other.mp4", seed=999)
    if other is None:
        pytest.skip("mp4v codec unavailable")
    assert _extracted_id(other) != registered_video["watermark_id"]


def test_video_watermark_stays_invisible(registered_video):
    """Stronger video alpha must remain visually lossless (PSNR > 40 dB)."""
    frame = _scene(640, 480, seed=42, motion_x=200)
    wm = we.embed_watermark_frame(frame, we.str_to_binary("v1d30abc"),
                                  alpha_min=we.VIDEO_ALPHA_MIN, alpha_max=we.VIDEO_ALPHA_MAX)
    mse = np.mean((frame.astype(np.float64) - wm.astype(np.float64)) ** 2)
    assert mse > 0, "watermark did not modify the frame at all"
    assert 20 * np.log10(255.0 / np.sqrt(mse)) > 40.0


def test_rescaled_video_still_caught_by_perceptual_hash(registered_video, tmp_path):
    """
    Rescaling shifts the DWT block grid, so watermark bits may not survive -- the
    perceptual-hash layer is what covers this case.
    """
    dst = _reencode(registered_video["watermarked"], str(tmp_path / "small.mp4"), scale=0.7)
    a = we.imagehash.hex_to_hash(we.get_video_perceptual_hash(registered_video["watermarked"]))
    b = we.imagehash.hex_to_hash(we.get_video_perceptual_hash(dst))
    assert (a - b) <= PHASH_THRESHOLD


def test_camera_recapture_still_caught_by_orb(registered_video, tmp_path):
    """
    Re-filming a screen destroys both watermark and hash; ORB structural matching on
    representative frames is the layer that has to catch it.
    """
    dst = _camera_recapture(registered_video["watermarked"], str(tmp_path / "recap.mp4"))
    kf_a = str(tmp_path / "kf_a.jpg")
    kf_b = str(tmp_path / "kf_b.jpg")
    assert we.extract_keyframe(registered_video["watermarked"], kf_a)
    assert we.extract_keyframe(dst, kf_b)
    assert we.calculate_orb_similarity(kf_b, kf_a) > BLOCK_THRESHOLD


def test_unrelated_videos_do_not_false_positive_on_orb(registered_video, tmp_path):
    other = _write_video(tmp_path / "other2.mp4", seed=1234)
    if other is None:
        pytest.skip("mp4v codec unavailable")
    kf_a = str(tmp_path / "ka.jpg")
    kf_b = str(tmp_path / "kb.jpg")
    we.extract_keyframe(registered_video["watermarked"], kf_a)
    we.extract_keyframe(other, kf_b)
    assert we.calculate_orb_similarity(kf_b, kf_a) <= BLOCK_THRESHOLD


@pytest.mark.parametrize("frame_count", [1, 3, we.VIDEO_EMBED_WORKERS - 1, we.VIDEO_EMBED_BATCH_SIZE,
                                         we.VIDEO_EMBED_BATCH_SIZE + 1, we.VIDEO_EMBED_BATCH_SIZE * 2 + 1])
def test_embedding_is_correct_at_batch_boundaries(tmp_path, frame_count):
    """
    Embedding batches frames across a thread pool for speed (see embed_video_watermark).
    Exercise frame counts below one worker, exactly at a batch edge, and straddling two
    batches, to catch off-by-one errors in the batching loop.
    """
    src = _write_video(tmp_path / f"src_{frame_count}.mp4", frames=frame_count, seed=3)
    if src is None:
        pytest.skip("mp4v codec unavailable in this environment")
    watermark_id = "batch123"
    out = str(tmp_path / f"out_{frame_count}.mp4")
    we.embed_video_watermark(src, we.str_to_binary(watermark_id), out)

    cap = cv2.VideoCapture(out)
    written = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    assert written == frame_count

    assert _extracted_id(out) == watermark_id


def test_embedding_is_deterministic_despite_threading(tmp_path):
    """Frame order must survive the thread pool: re-embedding the same clip twice
    must produce byte-identical output, not just a recoverable watermark."""
    src = _write_video(tmp_path / "src.mp4", frames=we.VIDEO_EMBED_BATCH_SIZE + 5, seed=9)
    if src is None:
        pytest.skip("mp4v codec unavailable in this environment")
    bits = we.str_to_binary("determin")
    out_a = str(tmp_path / "a.mp4")
    out_b = str(tmp_path / "b.mp4")
    we.embed_video_watermark(src, bits, out_a)
    we.embed_video_watermark(src, bits, out_b)

    def frames_of(path):
        cap = cv2.VideoCapture(path)
        out = []
        while True:
            ret, f = cap.read()
            if not ret:
                break
            out.append(f)
        cap.release()
        return out

    fa, fb = frames_of(out_a), frames_of(out_b)
    assert len(fa) == len(fb)
    assert all(np.array_equal(x, y) for x, y in zip(fa, fb))


def test_trimmed_copy_is_caught_by_multi_frame_orb_even_when_watermark_is_lost(registered_video, tmp_path):
    """
    Regression: comparing a single fixed keyframe position (e.g. 35% through each clip)
    cannot find a match when a copy is trimmed relative to the original -- a screen
    recording that starts a couple of seconds late, or a platform that clips the
    opening, shifts every relative position by a roughly constant offset. Verified
    against a real trimmed re-upload during development: the single-keyframe score was
    ~3 (indistinguishable from an unrelated video) while sampling several positions on
    both sides and taking the best pairwise score found the overlap at 100.

    This drops enough of the start that the trim alone pushes every fixed relative
    position noticeably out of alignment, standing in for that real-world case.
    """
    trimmed = _trim(registered_video["watermarked"], str(tmp_path / "trimmed_copy.mp4"), skip=15)

    # The single fixed keyframe (what verification used to compare) must NOT reliably
    # find this: that gap is exactly what motivated sampling multiple positions.
    single_frame_score = we.calculate_orb_similarity(trimmed, registered_video["watermarked"])

    # Multi-frame sampling (what verification does now) must find the match regardless.
    query_features = we.compute_orb_features_multi(we.orb_reference_paths(trimmed))
    candidate_features = we.compute_orb_features_multi(
        we.orb_reference_paths(registered_video["watermarked"]))
    multi_frame_score = we.best_orb_similarity_from_features(query_features, candidate_features)

    assert multi_frame_score > BLOCK_THRESHOLD, (
        f"multi-frame sampling should catch a trimmed copy (got {multi_frame_score}, "
        f"single-frame comparison scored {single_frame_score})"
    )


def test_watermarked_video_uses_a_browser_playable_codec(registered_video):
    """
    The watermarked clip is what an owner downloads and re-shares, so it has to play in
    a browser. OpenCV's default 'mp4v' writes MPEG-4 Part 2 (FMP4), which renders as an
    empty <video> element in every mainstream browser.
    """
    cap = cv2.VideoCapture(registered_video["watermarked"])
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    cap.release()
    codec = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4)).lower().strip("\x00")
    assert codec in ("h264", "avc1"), f"watermarked video encoded as {codec!r}, browsers cannot play it"


def test_media_type_mapping_is_per_extension():
    """A .webm served as video/mp4 (or a .png as image/jpeg) fails to render."""
    from app import upload_utils

    assert upload_utils.media_type_for("clip.mp4") == "video/mp4"
    assert upload_utils.media_type_for("clip.webm") == "video/webm"
    assert upload_utils.media_type_for("photo.png") == "image/png"
    assert upload_utils.media_type_for("photo.jpg") == "image/jpeg"


def test_keyframe_is_not_taken_from_the_very_first_frame(tmp_path):
    """
    Frame 0 carries the heaviest quantisation and real footage often opens on a
    fade-in, so the representative still must come from inside the clip.
    """
    path = str(tmp_path / "marked.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 15, (320, 240))
    if not writer.isOpened():
        pytest.skip("mp4v codec unavailable")
    black = np.zeros((240, 320, 3), dtype=np.uint8)
    bright = _scene(320, 240, seed=5)
    for i in range(40):
        writer.write(black if i < 5 else bright)
    writer.release()

    kf = str(tmp_path / "kf.jpg")
    assert we.extract_keyframe(path, kf)
    assert float(cv2.imread(kf).mean()) > 10.0, "keyframe came from the black opening frames"
