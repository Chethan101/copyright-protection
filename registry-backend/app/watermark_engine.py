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
from collections import OrderedDict
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

# ORB/RANSAC gates -- calibrated against this project's whole registry (every pair of
# different registered items, plus genuine copies of real registered photos/videos).
#
# Coincidental geometric matches between unrelated content never exceeded 36 inliers;
# genuine copies of real content started at 72 (an extreme 50% crop) and were
# typically in the hundreds (a real trimmed video re-upload: 507). The inlier ratio
# did NOT separate them (coincidences reached 57-90%), so the absolute count is the
# primary gate, set with margin on both sides.
#
# Earlier, smaller gates (20/25 inliers) let an unrelated photo be scored "100%"
# against an out-of-focus video frame -- and because that video belonged to the
# uploader, it waved through someone else's registered content.
MIN_GOOD_MATCHES_FOR_HOMOGRAPHY = 50
MIN_HOMOGRAPHY_INLIERS = 50
MIN_INLIER_RATIO = 40.0
# Share of each picture's detailed region a verified match must span (see
# orb_similarity_from_features). Genuine copies span >= 0.48 of at least one side
# (usually ~1.0); a crop is small only on the side it was cut from (as low as 0.04).
# Unrelated screen recordings can line up on shared UI chrome over a tiny region
# (~0.02-0.03 of both sides), and degenerate homographies collapse one side to ~0.
MIN_MATCH_COVERAGE = 0.25       # on at least one side
MIN_MATCH_COVERAGE_BOTH = 0.02  # on both sides


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_perceptual_hash(image_path, hash_size=16):
    img = Image.open(image_path).convert('RGB')
    return str(imagehash.phash(img, hash_size=hash_size))   # 16 -> 256-bit for accuracy


# A perceptual hash is the sign pattern of low-frequency DCT terms. On a near-uniform
# picture those terms are all ~0, so the pattern is noise and any two flat images look
# "identical" (measured: a plain blue and a plain green test image, 5 bits apart). Below
# this grey-level spread the hash is not used as evidence. Measured spread: flat test
# images 0.7-6.2; the dimmest of 25 real photos 16.1; registry median 32.
MIN_DETAIL_FOR_PHASH = 10.0


def perceptual_detail(path) -> float:
    """Grey-level standard deviation of a 64x64 rendering (video: a representative frame)."""
    if is_video_file(path):
        frame = _representative_frame(path)
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) if frame is not None else None
    else:
        img = Image.open(path)
    if img is None:
        return 0.0
    return float(np.asarray(img.convert('L').resize((64, 64), Image.LANCZOS), dtype=np.float32).std())


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

ORB_CACHE_SUFFIX = ".orb.npz"

# Descriptors are also held in-process, keyed on (path, size, mtime). The on-disk cache
# still matters for a cold start, but reading ~500 small archives per scan costs nearly
# as much as recomputing them; serving repeat verifications from memory removes both.
# Bounded so a large registry cannot grow the process without limit. A scan touches
# every entry, so a cap below the working set would thrash under LRU; at roughly 40KB
# per entry this ceiling costs tens of MB and covers a few hundred registered items.
ORB_MEMO_MAX_ENTRIES = 1024
_orb_memo = OrderedDict()


def _orb_cache_path(image_path: str) -> str:
    return image_path + ORB_CACHE_SUFFIX


def _memo_key(image_path: str):
    try:
        stat = os.stat(image_path)
    except OSError:
        return None
    return (os.path.abspath(image_path), stat.st_size, stat.st_mtime)


def _memo_get(key):
    if key is None or key not in _orb_memo:
        return False, None
    _orb_memo.move_to_end(key)
    return True, _orb_memo[key]


def _memo_put(key, features):
    if key is None:
        return
    _orb_memo[key] = features
    _orb_memo.move_to_end(key)
    while len(_orb_memo) > ORB_MEMO_MAX_ENTRIES:
        _orb_memo.popitem(last=False)


def _load_orb_cache(image_path: str):
    """
    Read cached descriptors, but only if they still describe the current file.

    The stored size/mtime guard means a replaced file can never be matched using a
    stale description of its previous contents.
    """
    cache_path = _orb_cache_path(image_path)
    if not os.path.exists(cache_path):
        return None
    try:
        stat = os.stat(image_path)
        with np.load(cache_path) as data:
            if int(data["size"]) != stat.st_size or float(data["mtime"]) != stat.st_mtime:
                return None
            if data["empty"]:
                return None
            return data["pts"], data["desc"]
    except Exception:
        return None


def _store_orb_cache(image_path: str, features):
    try:
        stat = os.stat(image_path)
        payload = {"size": stat.st_size, "mtime": stat.st_mtime, "empty": features is None}
        if features is None:
            payload["pts"] = np.empty((0, 2), dtype=np.float32)
            payload["desc"] = np.empty((0, 32), dtype=np.uint8)
        else:
            payload["pts"], payload["desc"] = features
        np.savez(_orb_cache_path(image_path), **payload)
    except Exception:
        pass  # A cache miss is only ever a slowdown, never a correctness problem.


def compute_orb_features(image_path: str, use_cache: bool = True):
    """
    Detect ORB keypoints/descriptors for one image, as (points, descriptors).

    Split out from the comparison so a single uploaded file can be described once and
    then matched against every registered record. Re-describing the query inside each
    comparison made verification cost scale with the size of the registry twice over.

    Descriptors are cached beside the file because registered content is immutable once
    stored, while detection was being repeated on every single verification -- measured
    at ~85% of the whole scan's cost. Only the keypoint coordinates are kept (that is
    all the homography needs), so the cache is two plain arrays.
    """
    memo_key = _memo_key(image_path) if use_cache else None
    if use_cache:
        hit, features = _memo_get(memo_key)
        if hit:
            return features
        cached = _load_orb_cache(image_path)
        if cached is not None:
            _memo_put(memo_key, cached)
            return cached

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
    features = None
    if descriptors is not None and len(keypoints) >= 5:
        features = (np.float32([kp.pt for kp in keypoints]), descriptors)

    if use_cache:
        _store_orb_cache(image_path, features)
        _memo_put(_memo_key(image_path), features)
    return features


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


def best_orb_match(features_list1, features_list2):
    """
    Strongest (score, inliers) across every pair of precomputed feature sets.

    Ranked by score, then by inliers: the cap makes many genuine matches score 100,
    and when the same picture is registered more than once, the record a copy was
    actually made from lines up far better (measured: 903 vs 317 inliers) -- which
    is what decides which registration to cite.
    """
    best = (0.0, 0)
    for f1 in features_list1:
        for f2 in features_list2:
            strength = orb_match_strength(f1, f2)
            if strength > best:
                best = strength
    return best


def best_orb_similarity_from_features(features_list1, features_list2) -> float:
    """
    Max ORB similarity across every pair of precomputed feature sets.

    Deliberately left serial: OpenCV already parallelises descriptor matching across
    every core internally, so wrapping this in a worker pool measured at 1.0-1.1x --
    pure added complexity for no gain.
    """
    best = 0.0
    for f1 in features_list1:
        for f2 in features_list2:
            score = orb_similarity_from_features(f1, f2)
            if score > best:
                best = score
    return best


def _bbox_area(points):
    xy = points.reshape(-1, 2)
    return float((xy[:, 0].max() - xy[:, 0].min()) * (xy[:, 1].max() - xy[:, 1].min()))


def _match_coverage(inlier_points, all_points):
    """
    How much of an image's feature-bearing region a verified match spans.

    Measured against the spread of ALL the image's keypoints rather than the full frame:
    many genuine pictures carry detail in only part of the frame (a subject on a plain
    background, a gradient sky), so a copy of them can never span the whole frame --
    but it does span most of the region that actually has detail.
    """
    if len(inlier_points) == 0 or len(all_points) == 0:
        return 0.0
    region = _bbox_area(all_points)
    return 0.0 if region <= 0 else min(1.0, _bbox_area(inlier_points) / region)


def orb_similarity_from_features(features1, features2) -> float:
    """Score two pre-computed ORB feature sets; see orb_match_strength."""
    return orb_match_strength(features1, features2)[0]


def orb_match_strength(features1, features2):
    """
    (score, inliers) for two pre-computed ORB feature sets (see compute_orb_features).

    The score is capped, so many genuine matches tie at 100; the inlier count is the raw
    evidence that breaks the tie (see best_orb_match).

    A visual match only counts once it is GEOMETRICALLY verified. Every way a copy is
    made -- exact re-upload, screenshot, crop, re-photograph, trimmed video -- leaves
    the copy as a projective transform of the original, so its matched points line up
    under one homography (measured on real copies: hundreds of inliers at 60-97%).
    Coincidental descriptor matches do not: measured on a real false block, an
    unrelated photo had 37 raw matches against an out-of-focus video frame but only 9
    that lined up (24%) -- and an earlier ratio-only score turned that into "100%"
    because the frame had just 94 keypoints in total.

    Two gates therefore stand between raw matches and any score:
      1. RANSAC homography with enough inliers at a high enough inlier ratio;
      2. those inliers must span a real part of the picture. Many registered clips are
         screen recordings sharing identical UI chrome (e.g. a "Stop recording" button):
         two unrelated recordings genuinely line up on that small region. A real copy
         covers a large share of at least one side's detailed region (a crop is small
         only on the side it was cut from), and some share of both -- which also rules
         out degenerate homographies that collapse a large region onto a point.
    """
    if features1 is None or features2 is None:
        return 0.0, 0
    pts1, des1 = features1
    pts2, des2 = features2

    min_kp = min(len(pts1), len(pts2))
    if min_kp == 0:
        return 0.0, 0

    # KNN matching with Lowe's ratio test (robust against glare, lighting, and camera noise)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = bf.knnMatch(des1, des2, k=2)
    good_matches = [m for pair in matches if len(pair) == 2
                    for m, n in [pair] if m.distance < 0.75 * n.distance]
    if len(good_matches) < MIN_GOOD_MATCHES_FOR_HOMOGRAPHY:
        return 0.0, 0

    src_pts = pts1[[m.queryIdx for m in good_matches]].reshape(-1, 1, 2)
    dst_pts = pts2[[m.trainIdx for m in good_matches]].reshape(-1, 1, 2)
    _, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if mask is None:
        return 0.0, 0
    inlier_mask = mask.ravel().astype(bool)
    inliers = int(inlier_mask.sum())
    inlier_ratio = (inliers / len(good_matches)) * 100.0
    if inliers < MIN_HOMOGRAPHY_INLIERS or inlier_ratio < MIN_INLIER_RATIO:
        return 0.0, 0

    cov1 = _match_coverage(src_pts[inlier_mask], pts1)
    cov2 = _match_coverage(dst_pts[inlier_mask], pts2)
    if max(cov1, cov2) < MIN_MATCH_COVERAGE or min(cov1, cov2) < MIN_MATCH_COVERAGE_BOTH:
        return 0.0, 0

    # Verified: the strength of the evidence sets the confidence.
    ratio_score = min(100.0, (len(good_matches) / min_kp) * 100.0 * 4.0)
    return round(float(max(ratio_score, min(99.0, inlier_ratio))), 2), inliers


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


def get_video_perceptual_hash_candidates(video_path: str, hash_size: int = 16):
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
                                     hash_size=hash_size))
        if digest not in seen:
            seen.add(digest)
            hashes.append(digest)
    return hashes or [get_perceptual_hash(video_path, hash_size)]

def extract_keyframe(video_path: str, output_image_path: str) -> bool:
    """Writes a representative still from the video for ORB/thumbnail matching."""
    frame = _representative_frame(video_path)
    if frame is None:
        return False
    cv2.imwrite(output_image_path, frame)
    return True
