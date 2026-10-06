import os

import cv2
import numpy as np
import pytest

from app import watermark_engine as we
from .conftest import make_test_video_bytes


def _make_frame(width=256, height=256, seed=0):
    rng = np.random.default_rng(seed)
    arr = rng.integers(40, 215, (height, width, 3), dtype=np.uint8)
    grad = np.linspace(0, 255, width, dtype=np.uint8)
    arr[:, :, 0] = np.tile(grad, (height, 1))
    return arr


def _bit_agreement(a: str, b: str) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return sum(x == y for x, y in zip(a[:n], b[:n])) / n


def test_embed_extract_roundtrip_in_memory_exact():
    """Clean, uncompressed round trip must recover the watermark bit-exactly."""
    frame = _make_frame(seed=1)
    watermark_id = "ab12cd34"
    bits = we.str_to_binary(watermark_id)

    wm_frame = we.embed_watermark_frame(frame, bits)
    extracted_bits = we.extract_watermark_frame(wm_frame, len(bits))

    assert extracted_bits == bits
    assert we.binary_to_str(extracted_bits) == watermark_id


def test_embed_is_visually_near_identical():
    """Invisibility sanity check: watermarked frame should stay very close to the original."""
    frame = _make_frame(seed=1)
    bits = we.str_to_binary("ab12cd34")
    wm_frame = we.embed_watermark_frame(frame, bits)

    diff = np.abs(frame.astype(np.int16) - wm_frame.astype(np.int16))
    assert diff.mean() < 5.0  # small average per-pixel change


def test_embed_extract_survives_jpeg_recompression():
    """Core robustness claim: watermark should survive a JPEG re-save."""
    frame = _make_frame(seed=2)
    watermark_id = "ef56gh78"
    bits = we.str_to_binary(watermark_id)
    wm_frame = we.embed_watermark_frame(frame, bits)

    ok, encoded = cv2.imencode(".jpg", wm_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    assert ok
    recompressed = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    extracted_bits = we.extract_watermark_frame(recompressed, len(bits))
    assert _bit_agreement(bits, extracted_bits) >= 0.9
    assert we.binary_to_str(extracted_bits) == watermark_id


def test_embed_extract_survives_resize_that_snaps_to_the_same_block_grid():
    """extract_watermark_frame() snaps its input down to the nearest multiple of 16
    per side before running DWT (see embed/extract dimension handling). Recovery is
    reliable exactly when the resized input snaps to the SAME grid the embed happened
    on -- e.g. a <1% resize here still floors to the original 320x320 grid."""
    frame = _make_frame(width=320, height=320, seed=3)
    watermark_id = "ij90kl12"
    bits = we.str_to_binary(watermark_id)
    wm_frame = we.embed_watermark_frame(frame, bits)

    h, w = wm_frame.shape[:2]
    resized = cv2.resize(wm_frame, (int(w * 1.01), int(h * 1.01)), interpolation=cv2.INTER_LINEAR)

    extracted_bits = we.extract_watermark_frame(resized, len(bits))
    assert we.binary_to_str(extracted_bits) == watermark_id


def test_embed_extract_does_not_survive_resize_that_shifts_the_block_grid():
    """Documents a real, current limitation (not something this pass fixes): despite
    the module docstring's "survives... mild resize" claim, ANY resize that snaps to a
    *different* 16-multiple grid than the embed-time image -- including a plain 10%
    downscale -- currently destroys recovery. Block indices are assigned sequentially
    over the LL grid, so changing the grid's row/col count shifts every block's bit
    assignment. This is a pre-existing algorithmic gap; recorded here so it's a known,
    tracked limitation instead of silent, undocumented behavior."""
    frame = _make_frame(width=320, height=320, seed=3)
    bits = we.str_to_binary("ij90kl12")
    wm_frame = we.embed_watermark_frame(frame, bits)

    h, w = wm_frame.shape[:2]
    resized = cv2.resize(wm_frame, (int(w * 0.9), int(h * 0.9)), interpolation=cv2.INTER_LINEAR)

    extracted_bits = we.extract_watermark_frame(resized, len(bits))
    assert _bit_agreement(bits, extracted_bits) < 0.75


def test_embed_extract_file_based_roundtrip_jpg(tmp_path):
    """Exercises the real disk-backed path the API uses (cv2.imread/imwrite at JPEG_QUALITY=97)."""
    frame = _make_frame(seed=4)
    src_path = str(tmp_path / "src.png")
    cv2.imwrite(src_path, frame)

    watermark_id = "mn34op56"
    bits = we.str_to_binary(watermark_id)
    out_path = str(tmp_path / "out.jpg")
    we.embed_watermark(src_path, bits, out_path)
    assert os.path.exists(out_path)

    extracted_bits = we.extract_watermark(out_path, len(bits))
    assert we.binary_to_str(extracted_bits) == watermark_id


def test_embed_nonexistent_source_raises():
    with pytest.raises(ValueError):
        we.embed_watermark("/no/such/file.png", we.str_to_binary("abcd1234"), "/tmp/out.jpg")


def test_extract_unreadable_file_returns_zero_bits_not_crash(tmp_path):
    bad_path = tmp_path / "not_an_image.png"
    bad_path.write_bytes(b"definitely not image data")
    result = we.extract_watermark(str(bad_path), 64)
    assert result == "0" * 64


def test_perceptual_hash_stable_for_same_image(tmp_path):
    frame = _make_frame(seed=5)
    path = str(tmp_path / "img.png")
    cv2.imwrite(path, frame)
    assert we.get_perceptual_hash(path) == we.get_perceptual_hash(path)


def test_perceptual_hash_differs_for_different_images(tmp_path):
    p1 = str(tmp_path / "a.png")
    p2 = str(tmp_path / "b.png")
    cv2.imwrite(p1, _make_frame(seed=10))
    cv2.imwrite(p2, _make_frame(seed=11))
    assert we.get_perceptual_hash(p1) != we.get_perceptual_hash(p2)


def test_video_embed_extract_roundtrip(tmp_path):
    data = make_test_video_bytes(frames=24, fps=8, seed=6)
    if data is None:
        pytest.skip("mp4v codec unavailable in this environment")
    src_path = str(tmp_path / "src.mp4")
    with open(src_path, "wb") as f:
        f.write(data)

    watermark_id = "qr78st90"
    bits = we.str_to_binary(watermark_id)
    out_path = str(tmp_path / "out.mp4")
    we.embed_video_watermark(src_path, bits, out_path)
    assert os.path.exists(out_path)

    extracted_bits = we.extract_video_watermark(out_path, len(bits))
    assert we.binary_to_str(extracted_bits) == watermark_id
