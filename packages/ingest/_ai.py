"""Shared AI client — DeepSeek-V4-Pro via HuggingFace Inference Providers router.

Uses the OpenAI-compatible HF router endpoint with Novita as the provider.
Set HF_TOKEN env var (HuggingFace access token with Inference Providers enabled).
Get a token at: https://huggingface.co/settings/tokens
"""
from __future__ import annotations
import os

from openai import OpenAI

MODEL = "deepseek-ai/DeepSeek-V4-Pro:novita"
_BASE_URL = "https://router.huggingface.co/v1"


def get_client() -> OpenAI:
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        raise EnvironmentError(
            "HF_TOKEN not set — get one from huggingface.co/settings/tokens"
        )
    return OpenAI(base_url=_BASE_URL, api_key=token)


def available() -> bool:
    """True if HF_TOKEN is present in environment."""
    return bool(os.environ.get("HF_TOKEN"))


def chat(messages: list[dict], temperature: float = 0) -> str:
    """Single chat completion via HF router. Returns empty string on any error."""
    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        return completion.choices[0].message.content or ""
    except EnvironmentError:
        return ""
    except Exception as e:
        import warnings  # noqa: PLC0415
        warnings.warn(
            f"HF router call failed ({type(e).__name__}): {e}. AI features disabled.",
            stacklevel=2,
        )
        return ""
