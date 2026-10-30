"""Model calls. One function, `complete(prompt)`, returns the model's text answer.

Uses a Databricks model-serving endpoint (Foundation Model APIs by default) through the OpenAI-compatible
client. Change LLM_ENDPOINT in .env to use another endpoint.
"""

from __future__ import annotations

import os

from . import config
from .clients import llm_client

LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_JSON_MODE = os.getenv("LLM_JSON_MODE", "true").lower() in {"1", "true", "yes"}  # set false if the endpoint rejects response_format


def complete(prompt: str, system: str = "You are a careful analyst. Answer with JSON only.") -> str:
    kwargs = {}
    if LLM_JSON_MODE:
        kwargs["response_format"] = {"type": "json_object"}
    response = llm_client().chat.completions.create(
        model=config.LLM_ENDPOINT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=LLM_MAX_TOKENS,
        **kwargs,
    )
    return response.choices[0].message.content or ""
