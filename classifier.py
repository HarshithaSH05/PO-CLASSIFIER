import json
import time

import streamlit as st
from groq import Groq
from prompts import SYSTEM_PROMPT

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

MODEL = "openai/gpt-oss-120b"

def parse_model_response(raw: str) -> dict | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def classify_po(po_description: str, supplier: str = "Not provided") -> str:
    """Return the raw model response as a string."""
    user_prompt = f"""
PD Description:
{po_description}

Supplier:
{supplier}
"""
    last_error = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
            else:
                break

    raise RuntimeError(f"Model request failed: {last_error}")
