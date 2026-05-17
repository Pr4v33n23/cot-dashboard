"""Shared AI client — DeepSeek-V4-Pro via HuggingFace Inference API.

All AI analysis (news sentiment + market synthesis) uses DeepSeek-V4-Pro
through HuggingFace. Set HF_TOKEN env var (HuggingFace access token).
Get a token at: https://huggingface.co/settings/tokens
"""
from __future__ import annotations
import os

from huggingface_hub import InferenceClient

MODEL = "deepseek-ai/DeepSeek-V4-Pro"


def get_client() -> InferenceClient:
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        raise EnvironmentError(
            "HF_TOKEN not set — get one from huggingface.co/settings/tokens"
        )
    return InferenceClient(model=MODEL, token=token)


def available() -> bool:
    """True if HF_TOKEN is present in environment."""
    return bool(os.environ.get("HF_TOKEN"))


def chat(messages: list[dict], temperature: float = 0) -> str:
    """Single chat completion. Returns the text content string."""
    client = get_client()
    resp = client.chat_completion(
        messages=messages,
        temperature=temperature,
        max_tokens=2048,
    )
    return resp.choices[0].message.content or ""
