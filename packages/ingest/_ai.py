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
    """Single chat completion. Returns empty string on any API error (graceful degradation)."""
    try:
        client = get_client()
        resp = client.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""
    except EnvironmentError:
        return ""
    except Exception as e:
        # 402 Payment Required, rate limits, network errors — never crash the caller
        import warnings  # noqa: PLC0415
        warnings.warn(f"DeepSeek API call failed ({type(e).__name__}): {e}. AI features disabled.", stacklevel=2)
        return ""
