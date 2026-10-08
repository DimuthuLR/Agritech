"""List Gemini models available to your API key, with vision support."""
import os
from app.core.config import settings
from google import genai


client = genai.Client(api_key=settings.gemini_api_key)

print(f"{'MODEL ID':50} {'INPUTS':40}")
print("-" * 95)
for m in client.models.list():
    actions = getattr(m, "supported_actions", []) or []
    if "generateContent" not in actions:
        continue
    inputs = getattr(m, "input_token_limit", "")
    # Show model name only (strip 'models/' prefix)
    name = m.name.replace("models/", "")
    print(f"{name:50} {str(actions)[:40]}")