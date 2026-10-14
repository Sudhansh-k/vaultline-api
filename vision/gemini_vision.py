"""vision/gemini_vision.py
=========================
Primary vision path: cache → Gemini → fallback (order controlled by VISION_MODE).

VISION_MODE   behaviour
-----------   ---------
auto          SHA-256 cache hit → return cached result;
              then try every Gemini model; on total failure → fallback_cv.
gemini        Cache + Gemini only; raise RuntimeError if all models fail.
fallback      Skip Gemini entirely; go straight to fallback_cv.

MOCK_VISION=1 still works and short-circuits everything.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections import OrderedDict

from dotenv import load_dotenv

load_dotenv()          # must run BEFORE any os.getenv() call below

# ── Env config ────────────────────────────────────────────────────────────────
MODELS      = [m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-2.0-flash").split(",") if m.strip()]
VISION_MODE = os.getenv("VISION_MODE", "auto").lower()   # "auto" | "gemini" | "fallback"
CACHE_MAX   = 200

# ── Gemini client (imported lazily avoided if VISION_MODE=fallback) ───────────
_gemini_client = None

def _get_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client()
    return _gemini_client


# ── Imports from sibling module ───────────────────────────────────────────────
from vision.fallback_cv import PhotoQualityError, analyze_photo, check_photo_quality
from pydantic import BaseModel
from google.genai import types


# ── In-memory LRU cache (SHA-256 → result dict) ───────────────────────────────
_cache: OrderedDict[str, dict] = OrderedDict()


def _cache_get(key: str) -> dict | None:
    if key in _cache:
        _cache.move_to_end(key)          # mark as most-recently used
        return _cache[key]
    return None


def _cache_put(key: str, value: dict) -> None:
    if key in _cache:
        _cache.move_to_end(key)
    _cache[key] = value
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)       # evict oldest


def cache_size() -> int:
    return len(_cache)


# ── Gemini schema ─────────────────────────────────────────────────────────────
class ConditionResult(BaseModel):
    condition_score: float
    defects: list[str]


PROMPT = (
    "You are inspecting a collectible item (e.g. a LEGO set or watch) and its packaging. "
    "Rate overall condition from 1.0 (heavily damaged) to 10.0 (mint, sealed). "
    "Consider: box creases, tears, dents, scratches, fading, seal integrity, wear. "
    "Return a condition_score and a list of short defect descriptions "
    "(empty list if none visible)."
)

RETRYABLE = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL", "DEADLINE")


# ── Gemini call (returns result dict or raises) ────────────────────────────────
def _call_gemini(image_bytes: bytes, mime_type: str) -> dict:
    client   = _get_client()
    last_err = None

    for model in MODELS:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        PROMPT,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ConditionResult,
                        temperature=0,
                    ),
                )
                r     = resp.parsed
                score = round(float(max(1.0, min(10.0, float(r.condition_score)))), 1)
                print(f"[gemini] used {model}")
                return {
                    "condition_score": score,
                    "defects":         list(r.defects),
                    "source":          "gemini",
                    "confidence":      "high",
                }
            except Exception as e:
                last_err = e
                msg = str(e)
                print(f"[gemini] {model} attempt {attempt + 1} failed: {msg[:120]}")
                if not any(code in msg for code in RETRYABLE):
                    break          # non-retryable (e.g. 404 model not found) → next model
                time.sleep(1.5)

    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")


# ── Public entry point ────────────────────────────────────────────────────────
def predict_condition(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Returns
    -------
    dict with keys: condition_score, defects, source, confidence
    (and optionally: metrics — present when source=="fallback")
    """
    # MOCK_VISION short-circuit (unchanged behaviour)
    if os.getenv("MOCK_VISION") == "1":
        return {
            "condition_score": 7.5,
            "defects":         ["mock result"],
            "source":          "mock",
            "confidence":      "high",
        }

    # Photo quality gate (skip only in fallback-skip-quality scenarios)
    check_photo_quality(image_bytes)

    mode = VISION_MODE

    # ── FALLBACK mode: skip Gemini entirely ───────────────────────────────────
    if mode == "fallback":
        return analyze_photo(image_bytes)

    # ── Cache lookup ──────────────────────────────────────────────────────────
    img_hash = hashlib.sha256(image_bytes).hexdigest()
    cached   = _cache_get(img_hash)
    if cached is not None:
        result = dict(cached)
        result["source"] = "cache"
        return result

    # ── GEMINI mode or AUTO: try Gemini ───────────────────────────────────────
    try:
        result = _call_gemini(image_bytes, mime_type)
        _cache_put(img_hash, result)
        return result
    except RuntimeError as err:
        if mode == "gemini":
            # Strict mode: propagate so the caller can raise 503
            raise
        # AUTO mode: log and fall through to fallback
        print(f"[vision] Gemini unavailable, switching to fallback_cv: {str(err)[:120]}")
        return analyze_photo(image_bytes)
