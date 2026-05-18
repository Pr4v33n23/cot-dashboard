# apps/api/src/chat.py
"""Chat endpoint logic — grounded DeepSeek analyst over live COT bundle."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

_PACKAGES = str(Path(__file__).resolve().parents[3] / "packages")
if _PACKAGES not in sys.path:
    sys.path.insert(0, _PACKAGES)

from ingest._ai import available, chat as ai_chat  # noqa: E402
from ingest.context_builder import build_context, context_to_str  # noqa: E402

_SYSTEM_TEMPLATE = """You are COT_LENS Analyst — a professional futures market analyst assistant grounded in live CFTC Commitment of Traders data.

TODAY'S LIVE DATA SNAPSHOT ({date}, {universe_size} markets loaded):
{context}

YOUR RULES:
1. ALWAYS ground answers in the data snapshot above. Quote specific values: COT index numbers, confluence scores, zone names.
2. When you mention a market, format its symbol in CAPS (CL, HG, ZS etc.) — the UI will auto-link them.
3. Never invent data not in the snapshot. If you don't have something, say so.
4. Physical commodities: use Williams/Briese commercial-hedger framing (commercials = smart money, specs = trend-followers).
5. Financial contracts (FX, indices, rates): use institutional flow framing (Dealers = sell-side hedge, Asset Managers = long-only, Leveraged Funds = directional specs).
6. Always clarify: COT positioning is CONTEXT for analysis, not a trade signal.
7. Be specific and concise. Traders don't want padding.

TONE: Direct, professional, data-driven. Like a Goldman desk analyst, not a chatbot."""


def build_system_prompt(bundle_context: dict) -> str:
    ctx_str = context_to_str(bundle_context)
    return _SYSTEM_TEMPLATE.format(
        date=bundle_context.get("date", ""),
        universe_size=bundle_context.get("universe_size", 0),
        context=ctx_str,
    )


def extract_cited_markets(text: str) -> list[str]:
    """Extract market symbols mentioned in the response."""
    known = {
        'CL','NG','RB','HO','BZ','GC','SI','HG','PL','PA','ALI',
        'ZC','ZS','ZW','KE','ZO','ZM','ZL','ZR','CC','KC','CT','SB','OJ','LBS',
        'LE','GF','HE','ES','NQ','YM','RTY','MES','MNQ','NIY',
        'ZB','ZN','ZF','ZT','FF','SR3',
        'EURUSD','GBPUSD','JPYUSD','AUDUSD','CADUSD','CHFUSD','NZDUSD',
        'MXNUSD','BRLUSD','NOKUSD','SEKUSD',
    }
    found = re.findall(r'\b([A-Z]{2,7})\b', text)
    return list(dict.fromkeys(s for s in found if s in known))


def answer(messages: list[dict], bundle) -> tuple[str, list[str], str]:
    """Call DeepSeek with context + conversation history.

    Returns: (reply_text, cited_markets, context_date)
    """
    ctx = build_context(bundle)
    system_prompt = build_system_prompt(ctx)

    full_messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": m["role"], "content": m["content"]} for m in messages],
    ]

    if not available():
        fallback = _deterministic_answer(messages, ctx)
        return fallback, extract_cited_markets(fallback), ctx.get("date", "")

    reply = ai_chat(full_messages, temperature=0.3)
    if not reply:
        reply = _deterministic_answer(messages, ctx)

    cited = extract_cited_markets(reply)
    return reply, cited, ctx.get("date", "")


def _deterministic_answer(messages: list[dict], ctx: dict) -> str:
    """Rule-based fallback answer when AI is unavailable."""
    last_msg = messages[-1]["content"].lower() if messages else ""
    markets = ctx.get("top_markets", [])

    if not markets:
        return "No market data loaded yet. Try again in a moment."

    if any(w in last_msg for w in ("interesting", "best", "top", "watch", "setup", "right now")):
        top = markets[:3]
        lines = ["Top setups right now (deterministic scoring, AI offline):"]
        for i, m in enumerate(top, 1):
            zones = ', '.join(m['zones_on']) if m['zones_on'] else 'none'
            lines.append(
                f"{i}. **{m['symbol']}** ({m['sector']}) — confluence {m['confluence_score']:.2f}, "
                f"COT index {m['cot_index']}, zones: {zones}"
            )
        return "\n".join(lines)

    top5 = ", ".join(m["symbol"] for m in markets[:5])
    return (
        f"AI synthesis is currently offline (HuggingFace credits). "
        f"Top markets by deterministic confluence: {top5}. "
        f"Check the Intelligence page for full breakdowns."
    )
