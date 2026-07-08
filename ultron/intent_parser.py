import json
import os
from openai import OpenAI

# Groq exposes an OpenAI-compatible endpoint, so we use the openai SDK
# but point it at Groq's server and use Groq's API key.
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ.get("GROQ_API_KEY"),
)

MODEL = "llama-3.3-70b-versatile"  # free tier, good enough for intent parsing

SYSTEM_PROMPT = """You convert a user's spoken/typed command into a single JSON object.

You MUST respond with ONLY valid JSON, no preamble, no markdown fences, no explanation.

The JSON must have exactly this shape:
{"action": "<one of: open, open_file, open_app, open_folder, unknown>", "target": "<string>"}

Rules:
- For almost all "open X" style requests, use "action": "open" with "target" set to
  just the name of the thing (e.g. "resume", "legobatman", "notepad", "downloads folder"
  becomes target "downloads"). This is the preferred, most flexible action - it searches
  by name automatically.
- Only use "open_file", "open_app", or "open_folder" if the user is extremely explicit
  about the type AND gives a full literal path (rare).
- If the command doesn't clearly map to opening something, use "unknown".
- "target" should be short - just the name or keyword, not a full sentence.
- Never invent actions outside the allowed list, even if the user asks for something else.
- Do not add commentary. Output JSON only.
"""


def parse_intent(user_text: str) -> dict:
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=200,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    )

    raw = (response.choices[0].message.content or "").strip()

    # Defensive cleanup in case the model wraps in fences despite instructions
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "unknown", "target": raw}

    if "action" not in parsed or "target" not in parsed:
        return {"action": "unknown", "target": raw}

    return parsed