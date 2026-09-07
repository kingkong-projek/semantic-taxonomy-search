#!/usr/bin/env python3
import json
import os
import urllib.request

MODEL = "gemma-4-26b-a4b-it"
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

prompt = """Du skapar träningsspråk för en svensk offentlig yrkestaxonomi.
Yrket är: Sjuksköterska, grundutbildad.
Beskrivningen är: Arbetar med omvårdnad av patienter, medicinska åtgärder och dokumentation.
Skriv exakt 8 korta svenska förstapersonsbeskrivningar som en vanlig person skulle kunna skriva utan att använda yrkestiteln. Variera mellan konkreta arbetsuppgifter, vardagligt språk, indirekt språk och telegramstil. Hitta inte på sådant som inte hör till yrket."""

schema = {
    "type": "object",
    "properties": {
        "phrases": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 8,
            "maxItems": 8,
            "description": "Exakt åtta korta svenska förstapersonsbeskrivningar."
        }
    },
    "required": ["phrases"],
    "additionalProperties": False
}

body = json.dumps({
    "model": MODEL,
    "input": prompt,
    "store": False,
    "response_format": {
        "type": "text",
        "mime_type": "application/json",
        "schema": schema
    },
    "generation_config": {
        "max_output_tokens": 700,
        "temperature": 0.3
    }
}, ensure_ascii=False).encode("utf-8")

req = urllib.request.Request(
    URL,
    data=body,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "x-goog-api-key": os.environ["GEMINI_API_KEY"]
    }
)
with urllib.request.urlopen(req, timeout=120) as response:
    payload = json.load(response)

text = ""
for step in reversed(payload.get("steps") or []):
    if step.get("type") == "model_output":
        text = "".join(
            str(part.get("text") or "")
            for part in (step.get("content") or [])
            if isinstance(part, dict) and part.get("type") == "text"
        ).strip()
        if text:
            break
if not text:
    raise RuntimeError("no model output text")
value = json.loads(text)
phrases = value.get("phrases") if isinstance(value, dict) else None
if not isinstance(phrases, list) or len(phrases) != 8 or not all(isinstance(x, str) and x.strip() for x in phrases):
    raise RuntimeError(f"schema contract failed: {value!r}")
print(json.dumps({"model": MODEL, "phrases": phrases, "usage": payload.get("usage") or {}}, ensure_ascii=False, indent=2))
