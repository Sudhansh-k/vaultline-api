"""vision/fallback_cv.py
======================
Pure-OpenCV / NumPy condition analyser used when Gemini is unavailable.

Public API
----------
    analyze_photo(image_bytes: bytes) -> dict
    check_photo_quality(image_bytes: bytes) -> None   # raises PhotoQualityError
    class PhotoQualityError(ValueError)

All numeric values returned are plain Python float / int — no numpy scalars.
"""

from __future__ import annotations

import os

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class PhotoQualityError(ValueError):
    """Raised when a photo fails the quality gate (extreme cases only)."""


# ---------------------------------------------------------------------------
# Quality gate  (called before spending Gemini quota)
# ---------------------------------------------------------------------------

def check_photo_quality(image_bytes: bytes) -> None:
    """
    Raise PhotoQualityError with a friendly message if the image is clearly
    unsuitable.  Only checks extreme/obviously-broken cases so that borderline
    photos still reach the AI.

    The gate can be disabled entirely with  PHOTO_QUALITY_GATE=0.
    """
    if os.getenv("PHOTO_QUALITY_GATE", "1") == "0":
        return

    # --- thresholds (lenient, env-overridable) ---
    min_side_px  = int(os.getenv("PQ_MIN_SIDE",        "200"))
    min_bright   = int(os.getenv("PQ_MIN_BRIGHTNESS",  "25"))
    max_bright   = int(os.getenv("PQ_MAX_BRIGHTNESS",  "245"))
    min_sharp    = int(os.getenv("PQ_MIN_SHARPNESS",   "15"))

    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise PhotoQualityError(
            "We couldn't read this image. Please upload a JPG or PNG."
        )

    h, w = img.shape[:2]
    min_side = min(h, w)
    gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bright   = float(np.mean(gray))
    sharp    = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    if min_side < min_side_px:
        raise PhotoQualityError(
            f"The photo is too small ({w}×{h} px). Please upload an image "
            f"that is at least {min_side_px} px on its shortest side."
        )
    if bright < min_bright:
        raise PhotoQualityError(
            "The photo is too dark. Please take it in better light and try again."
        )
    if bright > max_bright:
        raise PhotoQualityError(
            "The photo is heavily overexposed. Please reduce glare or move away "
            "from direct light and try again."
        )
    if sharp < min_sharp:
        raise PhotoQualityError(
            "The photo is too blurry for us to inspect the item properly. "
            "Please hold the camera steady and retake."
        )


# ---------------------------------------------------------------------------
# Main analyser
# ---------------------------------------------------------------------------

def analyze_photo(image_bytes: bytes) -> dict:
    """
    Analyse ``image_bytes`` with OpenCV/NumPy only.

    Returns
    -------
    dict with keys:
        condition_score : float  (clamped 3.0 – 7.0, 1 d.p.)
        defects         : list[str]
        confidence      : str   "low"
        source          : str   "fallback"
        metrics         : dict  (all plain float / int)
    """
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise PhotoQualityError(
            "We couldn't read this image. Please upload a JPG or PNG."
        )

    # --- resize so longest side ≤ 800 px ---
    h, w   = img.shape[:2]
    max_sz = 800
    scale  = min(1.0, max_sz / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)

    # --- raw metrics (all converted to plain Python float/int) ---
    gray       = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv        = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    sharpness      = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness     = float(np.mean(gray))
    glare_ratio    = float(np.mean(hsv[:, :, 2] > 245))
    edges          = cv2.Canny(gray, 80, 160)
    edge_density   = float(np.mean(edges > 0))
    mean_saturation = float(np.mean(hsv[:, :, 1]))
    orig_min_side  = int(min(h, w))          # before resize

    # --- scoring ---
    score   = 8.0
    defects: list[str] = []

    if glare_ratio > 0.08:
        score  -= 1.0
        defects.append("possible glare")

    if 0.10 <= edge_density <= 0.25:
        # linear: 0.0 penalty at edge_density=0.10 → 2.0 penalty at edge_density=0.25
        penalty = 2.0 * (edge_density - 0.10) / (0.25 - 0.10)
        score  -= float(penalty)
        defects.append("possible creases or surface wear")

    if mean_saturation < 60:
        score  -= 0.8
        defects.append("possible faded colours")

    if sharpness < 60:
        score  -= 0.7
        defects.append("image soft, details uncertain")

    score = round(float(max(3.0, min(7.0, score))), 1)

    return {
        "condition_score": score,
        "defects":         defects,
        "confidence":      "low",
        "source":          "fallback",
        "metrics": {
            "sharpness":       round(sharpness, 2),
            "brightness":      round(brightness, 2),
            "glare_ratio":     round(glare_ratio, 4),
            "edge_density":    round(edge_density, 4),
            "mean_saturation": round(mean_saturation, 2),
            "orig_min_side":   orig_min_side,
        },
    }
