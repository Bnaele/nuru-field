"""Gemini access and the prompts that are allowed to call it.

Three rules encoded here, all of them reactions to what the hackathon build did:

1. **The model is asked to describe, not to diagnose.** Prompts require visible
   evidence before interpretation, and label causes as possibilities.
2. **It never invents local data.** Weather, soil and prices come from the
   measured sources; the model is given them as context and told not to add its
   own numbers.
3. **Failures are translated.** A quota or overload error becomes a sentence a
   grower can act on, not a stack trace.
"""

from __future__ import annotations

import asyncio
import base64

from fastapi import HTTPException

from config import GEMINI_API_KEY, GEMINI_MODEL

# Google retired the 2.5 models for new projects and the "lite" variants have
# tiny free-tier quotas, so the fallback stays on 3.x flash.
FALLBACK_MODELS = ["gemini-3.6-flash"]

# Ceiling for the empty-response retry in answer(). One advisor reply fits in a
# few hundred tokens; 2,048 leaves room for the model's own reasoning on top.
MAX_RETRY_BUDGET = 2048

ADVISER_SYSTEM_PROMPT = """You are Nuru, a thoughtful agricultural field adviser for smallholder and first-time farmers, with a focus on South Africa while remaining useful globally.
Give practical, concise, plain-language advice. Explain uncertainty. You are not a substitute for a local agronomist, soil laboratory, veterinarian, or pesticide label. Never invent local records, disease diagnoses, exact chemical rates, soil nutrient values, or legal requirements. For potentially serious plant disease, pesticide, fertiliser, livestock, food-safety, or weather-risk questions, clearly say when to consult a local extension officer, certified agronomist, or other appropriate professional. Use metric units. Keep answers to a short helpful paragraph followed by 3-5 next steps when useful."""

PHOTO_PROMPT = """You are Nuru, an agricultural field adviser. Analyse this photo from a farmer and respond helpfully. The photo may show soil, plant leaves, fruit, a whole plant, or a pest.

Location: {location}
Measured field context: {context}

Begin your answer with one short line naming what the photo primarily shows, in this exact format:
**Subject:** soil | plant leaves | fruit | whole plant | pest | unclear

Then give three markdown bullet points adapted to that subject:
* **What I can see**: only visual details actually present in the photo (colour, texture, lesions, damage, growth stage, moisture, insects, mould). Do not invent anything.
* **What it might mean**: possible causes or conditions - labelled as possibilities, not diagnoses.
* **Recommended action**: one practical next step for the farmer.

Rules:
- If the photo is unclear or does not show anything agricultural, say so plainly and suggest a clearer, well-lit close-up.
- Never invent a crop species, disease name, exact nutrient value, or chemical treatment.
- Do not repeat or extend the measured field context above; it is there for your judgement only.
- If symptoms suggest something serious, recommend a local extension officer.
- Keep the whole answer under 160 words."""

_genai_client = None


def is_configured() -> bool:
    return bool(GEMINI_API_KEY)


def _get_client():
    global _genai_client
    if _genai_client is None:
        if not GEMINI_API_KEY:
            raise HTTPException(
                status_code=503,
                detail=(
                    "AI features are not configured. Add GEMINI_API_KEY to backend/.env, "
                    "then restart the API."
                ),
            )
        from google import genai

        _genai_client = genai.Client(api_key=GEMINI_API_KEY)
    return _genai_client


def decode_data_url(image: str) -> bytes:
    """Strip an optional `data:image/jpeg;base64,` prefix and decode."""
    raw = image or ""
    if "," in raw and raw.lstrip().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=False)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail="That photo could not be read. Please take a new JPG or PNG photo.",
        ) from error


async def answer(
    contents: list[dict],
    *,
    temperature: float = 0.35,
    max_output_tokens: int = 650,
) -> str:
    """Call Gemini with a fallback model chain and bounded retries."""
    from google.genai import types

    client = _get_client()

    sdk_contents = []
    for item in contents:
        parts = []
        for part in item.get("parts", []):
            if "text" in part:
                parts.append(types.Part.from_text(text=part["text"]))
            elif "inlineData" in part:
                inline = part["inlineData"]
                parts.append(
                    types.Part.from_bytes(
                        data=base64.b64decode(inline["data"]),
                        mime_type=inline["mimeType"],
                    )
                )
        sdk_contents.append(types.Content(role=item.get("role", "user"), parts=parts))

    last_error = ""
    # Deduplicate while keeping order: if GEMINI_MODEL is overridden to the same
    # name as a fallback we would otherwise retry one model eight times.
    models = list(dict.fromkeys([GEMINI_MODEL, *FALLBACK_MODELS]))
    budget = max_output_tokens
    for model_name in models:
        for attempt in range(4):
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=sdk_contents,
                    config=types.GenerateContentConfig(
                        system_instruction=ADVISER_SYSTEM_PROMPT,
                        temperature=temperature,
                        max_output_tokens=budget,
                    ),
                )
                text = (response.text or "").strip()
                if text:
                    return text
                # These models reason before they answer, and the reasoning is
                # charged to the same output budget. A tight cap is therefore
                # spent entirely on thinking and comes back as empty text, which
                # the caller then reported as "the AI service could not complete
                # that request" — a service failure for what is really a budget
                # one. Doubling and retrying tells the two apart.
                if budget < MAX_RETRY_BUDGET:
                    budget = min(budget * 2, MAX_RETRY_BUDGET)
                    continue
                last_error = "empty response"
                break
            except Exception as error:
                last_error = str(error)
                if "429" in last_error or "503" in last_error:
                    await asyncio.sleep(2 ** attempt)
                    continue
                break

    if "429" in last_error:
        raise HTTPException(
            status_code=503,
            detail="The AI has reached its free-tier limit. Please try again later.",
        )
    if "503" in last_error:
        raise HTTPException(
            status_code=503,
            detail="The AI is temporarily overloaded. Please try again in a moment.",
        )
    if last_error == "empty response":
        raise HTTPException(
            status_code=502,
            detail="The AI returned no answer for that request. Try asking in fewer words.",
        )
    raise HTTPException(
        status_code=502,
        detail="The AI service could not complete that request. Please try again.",
    )
