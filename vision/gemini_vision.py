import os, time
from google import genai
from google.genai import types
from pydantic import BaseModel

# Put model names from the list above here, most preferred first
MODELS = os.getenv("GEMINI_MODELS", "gemini-3.8-flash").split(",")
from dotenv import load_dotenv
load_dotenv()
client = genai.Client()

class ConditionResult(BaseModel):
    condition_score: float
    defects: list[str]

PROMPT = """You are inspecting a collectible item (e.g. a LEGO set or watch) and its packaging.
Rate overall condition from 1.0 (heavily damaged) to 10.0 (mint, sealed).
Consider: box creases, tears, dents, scratches, fading, seal integrity, wear.
Return a condition_score and a list of short defect descriptions
(empty list if none visible)."""

def predict_condition(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    if os.getenv("MOCK_VISION") == "1":
        return {"condition_score": 7.5, "defects": ["mock result"]}

    last_err = None
    for model in MODELS:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=model.strip(),
                    contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type), PROMPT],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ConditionResult,
                        temperature=0,
                    ),
                )
                r = resp.parsed
                score = max(1.0, min(10.0, float(r.condition_score)))
                return {"condition_score": round(score, 1), "defects": r.defects}
            except Exception as e:
                last_err = e
                print(f"[gemini] {model} attempt {attempt+1} failed: {str(e)[:120]}")
                time.sleep(2 ** attempt)
    raise last_err
