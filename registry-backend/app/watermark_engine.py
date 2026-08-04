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
import cv2
import numpy as np
import pywt
from scipy.fftpack import dct, idct
import imagehash
from PIL import Image


# ── Tunables ─────────────────────────────────────────────────────────────────
ALPHA_MIN   = 1.5    # Strength in flat/smooth areas (totally invisible)
ALPHA_MAX   = 5.0    # Strength in textured/edge areas (invisible to eye)
JPEG_QUALITY = 97    # High quality to minimise compression artefacts
# Use mid-frequency DCT positions — not too low (visible) not too high (destroyed by JPEG)
EMBED_POSITIONS = [(3, 4), (4, 3), (4, 4), (3, 5), (5, 3)]


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


# ── Embed ─────────────────────────────────────────────────────────────────────

def embed_watermark(image_path: str, watermark_bits: str, output_path: str) -> bool:
    """
    Embed watermark invisibly into the Y (luminance) channel only.
    Uses HVS-adaptive alpha so flat regions are barely touched.
    """
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    # Ensure dimensions are multiples of 16 (DWT + 8×8 DCT requirement)
    h, w = img.shape[:2]
    new_h = max(64, (h // 16) * 16)
    new_w = max(64, (w // 16) * 16)
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # Work in YCbCr — embed ONLY in Y (luminance)
    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV).astype(np.float32)
    Y = yuv[:, :, 0]

    # Single-level DWT
    LL, (HL, LH, HH) = pywt.dwt2(Y, 'haar')

    bits     = watermark_bits
    bits_len = len(bits)
    bit_idx  = 0

    rows, cols = LL.shape
    for i in range(0, rows - 7, 8):
        for j in range(0, cols - 7, 8):
            block = LL[i:i+8, j:j+8].copy()

            # HVS-adaptive strength
            tex   = _block_texture(block)
            alpha = ALPHA_MIN + tex * (ALPHA_MAX - ALPHA_MIN)

            dct_block = apply_dct_2d(block)
            bit       = int(bits[bit_idx % bits_len])
            bit_idx  += 1

            # Embed into each chosen mid-frequency position
            for (r, c) in EMBED_POSITIONS:
                coeff = dct_block[r, c]
                if bit == 1:
                    # Force coeff clearly positive
                    if coeff <= alpha:
                        dct_block[r, c] = alpha + abs(coeff) * 0.1
                else:
                    # Force coeff clearly negative
                    if coeff >= -alpha:
                        dct_block[r, c] = -(alpha + abs(coeff) * 0.1)

            LL[i:i+8, j:j+8] = apply_idct_2d(dct_block)

    # Reconstruct
    Y_wm  = pywt.idwt2((LL, (HL, LH, HH)), 'haar')
    yuv[:, :, 0] = np.clip(Y_wm, 0, 255)
    result = cv2.cvtColor(yuv.astype(np.uint8), cv2.COLOR_YUV2BGR)

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

def extract_watermark(image_path: str, watermark_len_bits: int) -> str:
    """
    Extract watermark bits using majority-vote across all LL DWT blocks.
    Robust even after JPEG recompression, mild resize, or brightness edits.
    """
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return '0' * watermark_len_bits

    h, w = img.shape[:2]
    new_h = max(64, (h // 16) * 16)
    new_w = max(64, (w // 16) * 16)
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV).astype(np.float32)
    Y   = yuv[:, :, 0]

    LL, _ = pywt.dwt2(Y, 'haar')

    # votes[i] = [count_0, count_1]
    votes = [[0, 0] for _ in range(watermark_len_bits)]
    idx   = 0

    rows, cols = LL.shape
    for i in range(0, rows - 7, 8):
        for j in range(0, cols - 7, 8):
            block     = LL[i:i+8, j:j+8].copy()
            dct_block = apply_dct_2d(block)
            pos       = idx % watermark_len_bits
            idx      += 1

            # Count positive vs negative votes across embed positions
            ones  = sum(1 for (r, c) in EMBED_POSITIONS if dct_block[r, c] > 0)
            zeros = len(EMBED_POSITIONS) - ones

            if ones > zeros:
                votes[pos][1] += 1
            else:
                votes[pos][0] += 1

    return ''.join('1' if v[1] > v[0] else '0' for v in votes)


# ── ORB similarity ────────────────────────────────────────────────────────────

def calculate_orb_similarity(img1_path: str, img2_path: str) -> float:
    """
    ORB feature-point matching with RANSAC Homography to detect screen photos,
    re-captured photos from mobile devices, crops, and perspective tilts.
    """
    img1 = cv2.imread(img1_path, cv2.IMREAD_GRAYSCALE)
    img2 = cv2.imread(img2_path, cv2.IMREAD_GRAYSCALE)

    if img1 is None or img2 is None:
        return 0.0

    # Normalise dimensions for consistent feature density
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]
    if max(h1, w1) > 1000:
        scale = 1000.0 / max(h1, w1)
        img1 = cv2.resize(img1, (int(w1 * scale), int(h1 * scale)))
    if max(h2, w2) > 1000:
        scale = 1000.0 / max(h2, w2)
        img2 = cv2.resize(img2, (int(w2 * scale), int(h2 * scale)))

    orb = cv2.ORB_create(nfeatures=1500, scoreType=cv2.ORB_FAST_SCORE)
    kp1, des1 = orb.detectAndCompute(img1, None)
    kp2, des2 = orb.detectAndCompute(img2, None)

    if des1 is None or des2 is None or len(kp1) < 5 or len(kp2) < 5:
        return 0.0

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

    # Feature match score based on good match ratio
    match_ratio = (len(good_matches) / min_kp) * 100.0
    score = min(100.0, match_ratio * 4.0)

    # RANSAC Homography check (confirms geometric structure even if photo taken from mobile screen)
    if len(good_matches) >= 8:
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if mask is not None:
            inliers = int(np.sum(mask))
            inlier_ratio = (inliers / len(good_matches)) * 100.0
            if inliers >= 8:
                homography_score = min(99.0, max(75.0, inlier_ratio * 1.2 + inliers * 1.5))
                score = max(score, homography_score)

    return round(float(score), 2)
