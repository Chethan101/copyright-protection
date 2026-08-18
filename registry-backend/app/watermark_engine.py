"""
Invisible HVS-Adaptive Spread-Spectrum Watermarking Engine
===========================================================
Key design goals:
  1. INVISIBLE  — perceptually transparent, no visible quality loss
  2. ROBUST     — survives JPEG re-save, screenshot, mild resize/crop
  3. DETECTABLE — majority-vote extraction across all DWT blocks

Technique:
  - DWT (Haar) decomposition → LL subband
  - 8x8 DCT on each LL block
  - HVS-adaptive alpha: higher in textured/edge blocks (human eye ignores noise there)
                        lower in flat/smooth blocks (eye is very sensitive there)
  - Embed ONLY in Y (luminance) channel — eye is far less sensitive to
    luminance changes in mid-frequency than to chroma changes
  - Alpha range: 1.5 (smooth) → 6.0 (textured) — completely invisible at JPEG q=97
  - Watermark bits spread across ALL blocks (spread-spectrum) for robustness
  - Majority-vote extraction: works even if 40% of blocks are corrupted
"""

import os
import shutil
import cv2
import numpy as np
import pywt
from scipy.fftpack import dct, idct
import imagehash
from PIL import Image
from concurrent.futures import ThreadPoolExecutor


# ── Tunables ─────────────────────────────────────────────────────────────────
ALPHA_MIN   = 1.5    # Strength in flat/smooth areas (totally invisible)
ALPHA_MAX   = 5.0    # Strength in textured/edge areas (invisible to eye)
# Video needs more embedding energy than a still. An uploaded clip is already lossily
# compressed before we ever see it, and we re-encode it on write, so the mid-frequency
# DCT band carries quantisation noise on the same order as the image-tuned alpha above --
# which swamps the watermark. Measured: these values recover the id exactly through the
# decode->embed->re-encode round trip at a mean pixel change of ~1.5/255 (imperceptible).
VIDEO_ALPHA_MIN = 10.0
VIDEO_ALPHA_MAX = 22.0
JPEG_QUALITY = 97    # High quality to minimise compression artefacts
# Use mid-frequency DCT positions — not too low (visible) not too high (destroyed by JPEG)
EMBED_POSITIONS = [(3, 4), (4, 3), (4, 4), (3, 5), (5, 3)]

# ORB/RANSAC gates. Measured against this project's own corpus: genuine derived copies
# (exact / screenshot / crop / camera re-capture) yield 500+ inliers at >=97% inlier ratio,
# while unrelated rich-texture photographs peak at ~8 chance inliers from <=15 good
# matches. Raised from an initial 20 after multi-frame video sampling surfaced a second
# class of false positive: low-texture, geometrically simple content (flat-color blocks
# on a gradient -- e.g. a screen recording or slideshow) has few enough keypoints that
# unrelated clips can reach 21-25 good matches at 76-91% inlier ratio by chance, since a
# small, generic feature set (axis-aligned corners) is far less discriminating than the
# rich texture of a real photo. A genuine match's *weakest* winning frame pair among
# real content still cleared 41 good matches, so 30 keeps a safety margin on both sides.
MIN_GOOD_MATCHES_FOR_HOMOGRAPHY = 30
MIN_HOMOGRAPHY_INLIERS = 25
MIN_INLIER_RATIO = 40.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_perceptual_hash(image_path):
    img = Image.open(image_path).convert('RGB')
    return str(imagehash.phash(img, hash_size=16))   # 256-bit for accuracy


def apply_dct_2d(block):
    return dct(dct(block.T, norm='ortho').T, norm='ortho')


def apply_idct_2d(block):
    return idct(idct(block.T, norm='ortho').T, norm='ortho')


def str_to_binary(s):
    return ''.join(format(ord(c), '08b') for c in s)


def binary_to_str(b):
    try:
        chars = [chr(int(b[i:i+8], 2)) for i in range(0, len(b)-7, 8)
                 if 32 <= int(b[i:i+8], 2) <= 126]
        return ''.join(chars)
    except Exception:
        return ''


def _block_texture(block):
    """
    Return a texture score in [0, 1] for an 8x8 block.
    High score = lots of edges/texture → can hide more energy.
    Low score  = smooth area → must be very subtle.
    """
    variance = float(np.var(block))
    # Sigmoid-like normalisation; calibrated so 'flat' areas < 0.2
    return min(1.0, variance / 800.0)


# ── Haar wavelet transform ────────────────────────────────────────────────────
# pywt's generic convolution path dominated the per-frame cost (~77ms of ~137ms on a
# 1080p frame, versus ~4ms for the DCT), which made registering even a short HD clip
# take tens of seconds. A single-level Haar transform is only sums and differences of
# adjacent samples, so it is expressed directly here. Inputs are always cropped to a
# multiple of 16 before this point, so no edge padding is needed. Verified numerically
# against pywt.dwt2/idwt2 (see tests) so watermarks stay bit-compatible.

_SQRT2 = np.float32(np.sqrt(2.0))


def dwt2_haar(X):
    """Single-level 2-D Haar DWT. Returns (LL, (cH, cV, cD)) matching pywt's layout."""
    lo = (X[:, 0::2] + X[:, 1::2]) / _SQRT2
    hi = (X[:, 0::2] - X[:, 1::2]) / _SQRT2
    LL = (lo[0::2] + lo[1::2]) / _SQRT2
    cH = (lo[0::2] - lo[1::2]) / _SQRT2
    cV = (hi[0::2] + hi[1::2]) / _SQRT2
    cD = (hi[0::2] - hi[1::2]) / _SQRT2
    return LL, (cH, cV, cD)


def dwt2_haar_LL(X):
    """
    Just the LL subband -- the only band this scheme reads or writes.

    Skipping the three detail bands cuts both the arithmetic and, more importantly, the
    memory traffic, which is what actually bounds this step on HD frames.
    """
    return (X[0::2, 0::2] + X[0::2, 1::2] + X[1::2, 0::2] + X[1::2, 1::2]) * np.float32(0.5)


def apply_LL_delta(Y, delta):
    """
    Apply a change made in the LL band back to the spatial frame, in place.

    The Haar transform is linear and perfectly reconstructing, so
    idwt2(LL + delta, details) == idwt2(LL, details) + idwt2(delta, 0) == Y + idwt2(delta, 0),
    and with zero detail bands that inverse is just a 2x2 block expansion scaled by a
    half. Written as four strided in-place adds: materialising the expanded array with
    np.repeat instead costs several full-frame allocations and is ~5x slower.
    """
    half = delta * np.float32(0.5)
    Y[0::2, 0::2] += half
    Y[0::2, 1::2] += half
    Y[1::2, 0::2] += half
    Y[1::2, 1::2] += half
    return Y


def idwt2_haar(LL, details):
    """Inverse of dwt2_haar."""
    cH, cV, cD = details
    rows, cols = LL.shape
    lo = np.empty((rows * 2, cols), dtype=np.float32)
    hi = np.empty((rows * 2, cols), dtype=np.float32)
    lo[0::2] = (LL + cH) / _SQRT2
    lo[1::2] = (LL - cH) / _SQRT2
    hi[0::2] = (cV + cD) / _SQRT2
    hi[1::2] = (cV - cD) / _SQRT2
    out = np.empty((rows * 2, cols * 2), dtype=np.float32)
    out[:, 0::2] = (lo + hi) / _SQRT2
    out[:, 1::2] = (lo - hi) / _SQRT2
    return out


# ── Batched block transforms ──────────────────────────────────────────────────
# A single HD frame holds several thousand 8x8 blocks. Transforming them one at a
# time from Python costs seconds per frame, which multiplied across a full clip is
# what made large-video verification exceed its request timeout. These helpers do
# the identical maths on every block in one vectorised pass. Block ordering is
# row-major (all blocks of row 0 left-to-right, then row 1, ...), matching the
# nested loops these replaced, so watermarks stay bit-compatible.

def _split_blocks(LL):
    """Split an LL subband into an (n_blocks, 8, 8) stack. Returns (None, None) if too small."""
    rows, cols = LL.shape
    n_rows, n_cols = rows // 8, cols // 8
    if n_rows == 0 or n_cols == 0:
        return None, None
    trimmed = LL[:n_rows * 8, :n_cols * 8]
    blocks = (trimmed.reshape(n_rows, 8, n_cols, 8)
                     .transpose(0, 2, 1, 3)
                     .reshape(-1, 8, 8))
    return np.ascontiguousarray(blocks), (n_rows, n_cols)


def _merge_blocks(blocks, LL, grid):
    """Write a block stack back into LL, leaving any trailing partial edge untouched."""
    n_rows, n_cols = grid
    merged = (blocks.reshape(n_rows, n_cols, 8, 8)
                    .transpose(0, 2, 1, 3)
                    .reshape(n_rows * 8, n_cols * 8))
    LL[:n_rows * 8, :n_cols * 8] = merged
    return LL


def _dct_2d_batch(blocks):
    """2-D DCT-II over the last two axes of a block stack."""
    return dct(dct(blocks, axis=1, norm='ortho'), axis=2, norm='ortho')


def _idct_2d_batch(blocks):
    """Inverse of _dct_2d_batch."""
    return idct(idct(blocks, axis=1, norm='ortho'), axis=2, norm='ortho')


def _bits_for_blocks(watermark_bits, n_blocks):
    """Repeat the watermark bit pattern across the block grid (spread spectrum)."""
    pattern = np.frombuffer(watermark_bits.encode('ascii'), dtype=np.uint8) - ord('0')
    return np.resize(pattern, n_blocks)


# ── Embed ─────────────────────────────────────────────────────────────────────

def embed_watermark_frame(img: np.ndarray, watermark_bits: str,
                          alpha_min: float = None, alpha_max: float = None) -> np.ndarray:
    """
    In-memory frame watermarking (0 disk I/O).

    alpha_min/alpha_max override the still-image defaults; video passes stronger values
    because its frames survive two lossy encodes. Read from module globals at call time
    so the tunables stay adjustable.
    """
    a_min = ALPHA_MIN if alpha_min is None else alpha_min
    a_max = ALPHA_MAX if alpha_max is None else alpha_max

    h, w = img.shape[:2]
    new_h = max(64, (h // 16) * 16)
    new_w = max(64, (w // 16) * 16)
    if (new_h, new_w) != (h, w):
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV).astype(np.float32)
    Y = yuv[:, :, 0]

    LL = dwt2_haar_LL(Y)

    blocks, grid = _split_blocks(LL)
    if blocks is None:
        return cv2.cvtColor(yuv.astype(np.uint8), cv2.COLOR_YUV2BGR)

    # HVS-adaptive strength per block, computed for every block at once.
    tex = np.minimum(1.0, blocks.var(axis=(1, 2)) / 800.0)
    alpha = (a_min + tex * (a_max - a_min)).astype(np.float32)

    dct_blocks = _dct_2d_batch(blocks)
    bits = _bits_for_blocks(watermark_bits, blocks.shape[0])

    for (r, c) in EMBED_POSITIONS:
        coeff = dct_blocks[:, r, c]
        magnitude = alpha + np.abs(coeff) * 0.1
        # bit 1 pushes the coefficient positive, bit 0 negative -- but only when it is
        # not already far enough in the right direction (matches the original per-block
        # conditional exactly, just evaluated across all blocks in one pass).
        dct_blocks[:, r, c] = np.where(
            bits == 1,
            np.where(coeff <= alpha, magnitude, coeff),
            np.where(coeff >= -alpha, -magnitude, coeff),
        )

    # Only the LL band changed, so feed the difference back through the inverse.
    delta = np.zeros_like(LL)
    _merge_blocks(_idct_2d_batch(dct_blocks) - blocks, delta, grid)

    yuv[:, :, 0] = np.clip(apply_LL_delta(Y, delta), 0, 255)
    return cv2.cvtColor(yuv.astype(np.uint8), cv2.COLOR_YUV2BGR)


def embed_watermark(image_path: str, watermark_bits: str, output_path: str) -> bool:
    """
    Embed watermark invisibly into the Y (luminance) channel only.
    Uses HVS-adaptive alpha so flat regions are barely touched.
    """
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    result = embed_watermark_frame(img, watermark_bits)

    # Save at high quality depending on file extension
    ext = os.path.splitext(output_path)[1].lower()
    if ext in ['.jpg', '.jpeg']:
        cv2.imwrite(output_path, result, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    elif ext == '.png':
        cv2.imwrite(output_path, result, [int(cv2.IMWRITE_PNG_COMPRESSION), 1])
    else:
        cv2.imwrite(output_path, result)
    return True


# ── Extract ───────────────────────────────────────────────────────────────────

def extract_watermark_frame_votes(img: np.ndarray, watermark_len_bits: int):
    """
    Per-bit [zeros, ones] vote tallies for a single frame (0 disk I/O).

    Returning raw tallies rather than a collapsed bit-string lets video extraction
    pool evidence across frames: a bit that is marginal in one frame contributes in
    proportion to its actual support instead of casting a full-strength vote.
    """
    h, w = img.shape[:2]
    new_h = max(64, (h // 16) * 16)
    new_w = max(64, (w // 16) * 16)
    if (new_h, new_w) != (h, w):
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV).astype(np.float32)
    Y   = yuv[:, :, 0]

    LL = dwt2_haar_LL(Y)

    blocks, _ = _split_blocks(LL)
    if blocks is None:
        return [[0, 0] for _ in range(watermark_len_bits)]

    dct_blocks = _dct_2d_batch(blocks)

    # Each block casts one vote, decided by the sign of its embedding positions.
    positive = np.zeros(blocks.shape[0], dtype=np.int16)
    for (r, c) in EMBED_POSITIONS:
        positive += (dct_blocks[:, r, c] > 0)
    votes_one = positive > (len(EMBED_POSITIONS) - positive)

    bit_index = np.arange(blocks.shape[0]) % watermark_len_bits
    ones = np.bincount(bit_index[votes_one], minlength=watermark_len_bits)
    zeros = np.bincount(bit_index[~votes_one], minlength=watermark_len_bits)

    return [[int(z), int(o)] for z, o in zip(zeros, ones)]


def extract_watermark_frame(img: np.ndarray, watermark_len_bits: int) -> str:
    """
    In-memory frame watermark extraction (0 disk I/O).
    """
    votes = extract_watermark_frame_votes(img, watermark_len_bits)
    return ''.join('1' if v[1] > v[0] else '0' for v in votes)


def extract_watermark(image_path: str, watermark_len_bits: int) -> str:
    """
    Extract watermark bits using majority-vote across all LL DWT blocks.
    Robust even after JPEG recompression, mild resize, or brightness edits.
    """
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return '0' * watermark_len_bits

    return extract_watermark_frame(img, watermark_len_bits)


# ── ORB similarity ────────────────────────────────────────────────────────────

def compute_orb_features(image_path: str):
    """
    Detect ORB keypoints/descriptors for one image.

    Split out from the comparison so a single uploaded file can be described once and
    then matched against every registered record. Re-describing the query inside each
    comparison made verification cost scale with the size of the registry twice over.
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None

    # Normalise dimensions for consistent feature density
    h, w = img.shape[:2]
    if max(h, w) > 1000:
        scale = 1000.0 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    orb = cv2.ORB_create(nfeatures=1500, scoreType=cv2.ORB_FAST_SCORE)
    keypoints, descriptors = orb.detectAndCompute(img, None)
    if descriptors is None or len(keypoints) < 5:
        return None
    return keypoints, descriptors


def calculate_orb_similarity(img1_path: str, img2_path: str) -> float:
    """
    ORB feature-point matching with RANSAC Homography to detect screen photos,
    re-captured photos from mobile devices, crops, and perspective tilts.
    """
    return orb_similarity_from_features(compute_orb_features(img1_path),
                                        compute_orb_features(img2_path))


# Relative positions sampled across a video for ORB comparison. A single keyframe
# cannot reliably represent a whole clip: two uploads of "the same" video routinely
# differ by a trim at the start (a screen recording that didn't start at frame zero, a
# platform that clips the first few seconds), which shifts every relative position by a
# roughly constant offset -- comparing only one fixed position on each side can land on
# two frames that are seconds apart in a fast-motion scene and miss a genuine match
# entirely. Sampling several positions on both sides and taking the best pairwise score
# finds the overlapping footage regardless of where the trim boundary falls. Measured
# against a real trimmed re-upload: the single-keyframe score was ~3 (indistinguishable
# from an unrelated video); the best pairwise score across this sampling was 100.
VIDEO_ORB_SAMPLE_POSITIONS = (0.15, 0.25, 0.35, 0.5, 0.65, 0.75)


def extract_orb_sample_frames(video_path, positions=VIDEO_ORB_SAMPLE_POSITIONS):
    """
    Extract (and cache) several frames spread across a video, for ORB comparison.

    Results are cached as files next to the source video (like the single
    `_keyframe.jpg`), so this cost is paid at most once per stored video, not once per
    verification request -- only ever-registered content pays it, and only the first
    time it's compared against. A single reused VideoCapture handle is used for all
    seeks in one call (measured ~2x cheaper than reopening per seek).
    """
    paths = []
    to_extract = []
    for i, pos in enumerate(positions):
        cached = f"{video_path}_orbkf{i}.jpg"
        if os.path.exists(cached):
            paths.append(cached)
        else:
            to_extract.append((pos, cached))
    if not to_extract:
        return paths

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return paths
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return paths
        for pos, cached in to_extract:
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(int(total * pos), total - 1))
            ret, frame = cap.read()
            if ret and frame is not None:
                cv2.imwrite(cached, frame)
                paths.append(cached)
    finally:
        cap.release()
    return paths


def orb_reference_paths(path):
    """Frame path(s) to compare against: several samples for a video, itself for a still."""
    if is_video_file(path):
        return extract_orb_sample_frames(path)
    return [path]


def compute_orb_features_multi(paths):
    """ORB features for each path, skipping any that fail to load or lack keypoints."""
    return [f for f in (compute_orb_features(p) for p in paths) if f is not None]


def best_orb_similarity_from_features(features_list1, features_list2) -> float:
    """Max ORB similarity across every pair of precomputed feature sets."""
    best = 0.0
    for f1 in features_list1:
        for f2 in features_list2:
            score = orb_similarity_from_features(f1, f2)
            if score > best:
                best = score
    return best


def orb_similarity_from_features(features1, features2) -> float:
    """Score two pre-computed ORB feature sets (see compute_orb_features)."""
    if features1 is None or features2 is None:
        return 0.0
    kp1, des1 = features1
    kp2, des2 = features2

    # KNN matching with Lowe's ratio test (robust against glare, lighting, and camera noise)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = bf.knnMatch(des1, des2, k=2)

    good_matches = []
    for m_pair in matches:
        if len(m_pair) == 2:
            m, n = m_pair
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)

    min_kp = min(len(kp1), len(kp2))
    if min_kp == 0:
        return 0.0

    # Feature match score based on good match ratio. Gated on an ABSOLUTE match count,
    # not just the ratio: when one image has very few keypoints (a blurry or otherwise
    # low-texture frame), a handful of coincidental matches becomes a large fraction of
    # a tiny denominator and inflates the ratio, even against genuinely unrelated content.
    # Measured on a real out-of-focus frame: 17 matches out of 90 keypoints scored 75.6
    # (well above the 50 block threshold) against completely unrelated footage, while a
    # confirmed genuine match on the same clip produced 544 matches. The gate below is
    # shared with the homography check for the same reason: both need enough raw
    # correspondence to be trustworthy at all, not just a good proportion of a small set.
    score = min(100.0, (len(good_matches) / min_kp) * 100.0 * 4.0) \
        if len(good_matches) >= MIN_GOOD_MATCHES_FOR_HOMOGRAPHY else 0.0

    # RANSAC Homography check (confirms geometric structure even if photo taken from mobile screen).
    # Gates are deliberately strict: unrelated images routinely produce a handful of chance
    # inliers, while a genuine re-capture/crop/screenshot of the same content yields hundreds
    # at a near-total inlier ratio. Scoring is proportional to the measured inlier ratio --
    # never a fixed floor, which would turn any chance correspondence into a confident match.
    if len(good_matches) >= MIN_GOOD_MATCHES_FOR_HOMOGRAPHY:
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if mask is not None:
            inliers = int(np.sum(mask))
            inlier_ratio = (inliers / len(good_matches)) * 100.0
            if inliers >= MIN_HOMOGRAPHY_INLIERS and inlier_ratio >= MIN_INLIER_RATIO:
                score = max(score, min(99.0, inlier_ratio))

    return round(float(score), 2)


# ── Video Support ─────────────────────────────────────────────────────────────

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.webm', '.mkv'}

# How many frames to pool when reading a watermark out of a video, and where to take
# the representative still from. Frame 0 is a poor choice for both: it carries the
# heaviest I-frame quantisation and real footage often opens on a fade-in or slate.
VIDEO_SAMPLE_FRAMES = 40
VIDEO_MIN_SAMPLE_FRAMES = 8
# Frame embedding is independent per frame and NumPy/SciPy release the GIL during their
# C-level work, so a thread pool gets real speedup (measured ~3.6x at 8 workers on a
# 16-core machine). Capped rather than set to cpu_count(): gains flatten past ~8 because
# the pipeline is memory-bandwidth-bound, not compute-bound. Batched (not "decode the
# whole clip") so peak memory stays bounded regardless of video length.
VIDEO_EMBED_WORKERS = min(8, os.cpu_count() or 4)
VIDEO_EMBED_BATCH_SIZE = VIDEO_EMBED_WORKERS * 3
# Recovery confidence comes from the total number of block votes behind each bit, not
# from the frame count itself. One HD frame already carries ~100 votes per bit, while a
# small frame carries barely one -- so the sample count is derived from the frame's own
# block yield. Without this, HD clips paid for ~40 full-resolution decodes they did not
# need, which is what pushed verification past its request timeout.
VIDEO_TARGET_VOTES_PER_BIT = 400
KEYFRAME_POSITION = 0.35

# Encoders to try, in order, when writing the watermarked clip. H.264 in an MP4
# container is what browsers can actually play back.
VIDEO_CODEC_PREFERENCE = ('avc1', 'H264', 'mp4v')
BROWSER_PLAYABLE_VIDEO_EXT = '.mp4'


def is_video_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


def _frames_needed_for(width: int, height: int, watermark_len_bits: int) -> int:
    """
    How many frames to sample so each bit accumulates enough independent block votes.

    A frame contributes (blocks / bits) votes per bit, so large frames need far fewer
    samples than small ones to reach the same confidence.
    """
    if width <= 0 or height <= 0 or watermark_len_bits <= 0:
        return VIDEO_SAMPLE_FRAMES
    # Mirror the geometry used during extraction: crop to a multiple of 16, then the
    # Haar DWT halves each dimension before the 8x8 block grid is laid out.
    usable_w = max(64, (width // 16) * 16) // 2
    usable_h = max(64, (height // 16) * 16) // 2
    blocks = (usable_h // 8) * (usable_w // 8)
    if blocks <= 0:
        return VIDEO_SAMPLE_FRAMES
    votes_per_frame = max(1, blocks // watermark_len_bits)
    needed = -(-VIDEO_TARGET_VOTES_PER_BIT // votes_per_frame)  # ceil division
    return max(VIDEO_MIN_SAMPLE_FRAMES, min(VIDEO_SAMPLE_FRAMES, needed))


def _first_frame(video_path: str):
    """The opening frame -- only needed for backwards-compatible hash comparison."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    try:
        ret, frame = cap.read()
        return frame if ret else None
    finally:
        cap.release()


def _representative_frame(video_path: str):
    """Read a frame from a stable point inside the video, falling back to the first."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total > 1:
            target = int(total * KEYFRAME_POSITION)
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(target, total - 1))
            ret, frame = cap.read()
            if ret and frame is not None:
                return frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
        return frame if ret else None
    finally:
        cap.release()

def _open_browser_playable_writer(output_path: str, fps: float, size):
    """
    Open a VideoWriter using a codec browsers can actually decode.

    OpenCV's usual 'mp4v' tag writes MPEG-4 Part 2 (FMP4), which no mainstream browser
    plays -- a watermarked clip encoded that way renders as an empty <video> element in
    the feed. H.264 is tried first and 'mp4v' kept only as a last-resort fallback so the
    pipeline still functions on builds without an H.264 encoder.
    """
    last_error = None
    for tag in VIDEO_CODEC_PREFERENCE:
        try:
            writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*tag), fps, size)
        except Exception as exc:  # pragma: no cover - build-specific
            last_error = exc
            continue
        if writer.isOpened():
            return writer
        writer.release()
    raise ValueError(f"No usable video codec for {output_path} ({last_error})")


def embed_video_watermark(video_path: str, watermark_bits: str, output_path: str) -> bool:
    """
    Frame-by-frame DWT-DCT watermarking for videos (0 disk I/O beyond the output file).

    Each frame is embedded independently, and the underlying NumPy/SciPy array ops
    release the GIL, so a thread pool gets real wall-clock speedup here (measured ~3.6x
    at 8 workers) with none of the process-pool overhead of pickling frames or spawning
    interpreters. Frames are processed in bounded batches rather than decoding the whole
    clip up front, so peak memory stays proportional to the batch size rather than to
    video length -- an hour-long clip must not try to hold itself in RAM at once.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    new_w = max(64, (w // 16) * 16)
    new_h = max(64, (h // 16) * 16)

    out = _open_browser_playable_writer(output_path, fps, (new_w, new_h))

    def embed_one(frame):
        return embed_watermark_frame(frame, watermark_bits,
                                     alpha_min=VIDEO_ALPHA_MIN, alpha_max=VIDEO_ALPHA_MAX)

    try:
        with ThreadPoolExecutor(max_workers=VIDEO_EMBED_WORKERS) as pool:
            while True:
                batch = []
                for _ in range(VIDEO_EMBED_BATCH_SIZE):
                    ret, frame = cap.read()
                    if not ret:
                        break
                    batch.append(frame)
                if not batch:
                    break
                # executor.map preserves input order, so batches write out identically
                # to the original sequential loop.
                for wm_frame in pool.map(embed_one, batch):
                    out.write(wm_frame)
    finally:
        cap.release()
        out.release()

    return True

def extract_video_watermark(video_path: str, watermark_len_bits: int) -> str:
    """
    Extract the watermark by pooling per-block votes across many frames.

    Lossy inter-frame codecs leave each individual frame only ~97% accurate, and the
    very first frame is typically the worst (heaviest I-frame quantisation, and in real
    footage often a fade-in). Sampling just a couple of frames therefore lets a single
    bad frame flip bits outright. Pooling raw block votes over a wide, evenly spread
    sample makes recovery robust to any handful of degraded frames.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return '0' * watermark_len_bits

    totals = np.zeros((watermark_len_bits, 2), dtype=np.int64)
    sampled = 0

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        target_frames = _frames_needed_for(
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
            watermark_len_bits,
        )

        if total_frames > target_frames * 2:
            # Long clip: seek straight to evenly spread positions. Decoding every frame
            # just to skip most of them is what dominated the cost on HD footage.
            targets = np.linspace(0, total_frames - 1, target_frames, dtype=int)
            for target in targets:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(target))
                ret, frame = cap.read()
                if not ret:
                    continue
                totals += extract_watermark_frame_votes(frame, watermark_len_bits)
                sampled += 1
        else:
            # Short clip: sequential reading is cheaper than seeking.
            step = max(1, total_frames // target_frames) if total_frames > 0 else 1
            frame_idx = 0
            while sampled < target_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % step == 0:
                    totals += extract_watermark_frame_votes(frame, watermark_len_bits)
                    sampled += 1
                frame_idx += 1
    finally:
        cap.release()

    if sampled == 0:
        return '0' * watermark_len_bits

    return ''.join('1' if one > zero else '0' for zero, one in totals)

def get_video_perceptual_hash(video_path: str) -> str:
    """Perceptual hash of a representative video frame (0 disk I/O)."""
    frame = _representative_frame(video_path)
    if frame is None:
        return get_perceptual_hash(video_path)
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return str(imagehash.phash(pil_img, hash_size=16))


def get_video_perceptual_hash_candidates(video_path: str):
    """
    Perceptual hashes for the frame positions a stored video hash could have come from.

    The representative frame moved off frame 0 (it is the most compressed frame and real
    footage often opens on a fade-in). Records written before that change hold a frame-0
    hash, and re-hashing them is not an option because the hash is the key the
    registration was notarised under on-chain. Comparing against both positions keeps the
    perceptual-hash layer working for old and new records alike.
    """
    hashes = []
    seen = set()
    for frame in (_representative_frame(video_path), _first_frame(video_path)):
        if frame is None:
            continue
        digest = str(imagehash.phash(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                                     hash_size=16))
        if digest not in seen:
            seen.add(digest)
            hashes.append(digest)
    return hashes or [get_perceptual_hash(video_path)]

def extract_keyframe(video_path: str, output_image_path: str) -> bool:
    """Writes a representative still from the video for ORB/thumbnail matching."""
    frame = _representative_frame(video_path)
    if frame is None:
        return False
    cv2.imwrite(output_image_path, frame)
    return True
