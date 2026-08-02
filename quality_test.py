"""
Quality test: measures PSNR (Peak Signal-to-Noise Ratio) and SSIM
between original and watermarked image, then verifies detection still works.

PSNR > 40 dB = visually lossless (broadcast standard)
PSNR > 45 dB = completely imperceptible
SSIM > 0.99  = near-perfect structural similarity
"""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'registry-backend'))

import numpy as np
import cv2
from PIL import Image, ImageDraw
import random, time

# Create test image (200x200, colourful, with texture)
img = Image.new('RGB', (400, 400), color=(random.randint(50,200), random.randint(80,180), random.randint(40,160)))
draw = ImageDraw.Draw(img)
for _ in range(30):
    x, y = random.randint(0,380), random.randint(0,380)
    draw.ellipse([x,y,x+20,y+20], fill=(random.randint(0,255), random.randint(0,255), random.randint(0,255)))
draw.text((10, 10), f"Test {time.time():.0f}", fill=(255,255,255))

orig_path = "registry-backend/app/uploads/test_orig_quality.jpg"
wm_path   = "registry-backend/app/watermarked/test_wm_quality.jpg"
os.makedirs(os.path.dirname(orig_path), exist_ok=True)
os.makedirs(os.path.dirname(wm_path), exist_ok=True)
img.save(orig_path, quality=97)

# Import watermark engine
from registry-backend.app import watermark_engine  # noqa

watermark_id   = "ab12cd34"
watermark_bits = watermark_engine.str_to_binary(watermark_id)

print(f"Watermark ID : {watermark_id}")
print(f"Watermark bits: {len(watermark_bits)} bits")

watermark_engine.embed_watermark(orig_path, watermark_bits, wm_path)

# Measure PSNR
orig_cv = cv2.imread(orig_path).astype(np.float64)
wm_cv   = cv2.imread(wm_path).astype(np.float64)

if orig_cv.shape != wm_cv.shape:
    wm_cv = cv2.resize(wm_cv, (orig_cv.shape[1], orig_cv.shape[0]))

mse  = np.mean((orig_cv - wm_cv) ** 2)
psnr = 10 * np.log10(255**2 / mse) if mse > 0 else float('inf')

print(f"\nPSNR         : {psnr:.2f} dB  (>40=lossless, >45=imperceptible)")

# SSIM approximation
def ssim_channel(a, b):
    c1, c2 = 6.5025, 58.5225
    mu1, mu2 = a.mean(), b.mean()
    s1  = ((a - mu1)**2).mean()
    s2  = ((b - mu2)**2).mean()
    s12 = ((a - mu1)*(b - mu2)).mean()
    return ((2*mu1*mu2+c1)*(2*s12+c2)) / ((mu1**2+mu2**2+c1)*(s1+s2+c2))

ssim = np.mean([ssim_channel(orig_cv[:,:,ch], wm_cv[:,:,ch]) for ch in range(3)])
print(f"SSIM         : {ssim:.4f}  (>0.99=near-perfect, 1.0=identical)")

# Verify watermark is still detectable
extracted_bits = watermark_engine.extract_watermark(wm_path, len(watermark_bits))
extracted_id   = watermark_engine.binary_to_str(extracted_bits)
bit_accuracy   = sum(a==b for a,b in zip(watermark_bits, extracted_bits)) / len(watermark_bits) * 100

print(f"\nOriginal ID  : {watermark_id}")
print(f"Extracted ID : {extracted_id}")
print(f"Bit accuracy : {bit_accuracy:.1f}%")
print(f"Match        : {'✅ DETECTED' if extracted_id == watermark_id else '⚠️  PARTIAL'}")

print("\n" + "="*50)
if psnr > 45:
    print("✅ IMPERCEPTIBLE - watermark is completely invisible")
elif psnr > 40:
    print("✅ LOSSLESS - watermark meets broadcast quality standard")
else:
    print("⚠️  Visible distortion - needs tuning")
