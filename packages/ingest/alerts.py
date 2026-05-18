"""Alert system — persistent JSON store + evaluation engine."""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ALERT_FILE = Path(__file__).resolve().parents[2] / "research" / "data" / "alerts.json"

Condition = Literal["above", "below", "crosses_above", "crosses_below"]
Field = Literal["cot_index_comm", "confluence_score", "n_zones", "comm_spec_divergence"]


def _load() -> list[dict]:
    if not ALERT_FILE.exists():
        return []
    try:
        return json.loads(ALERT_FILE.read_text())
    except Exception:
        return []


def _save(alerts: list[dict]) -> None:
    ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ALERT_FILE.write_text(json.dumps(alerts, indent=2, default=str))


def list_alerts() -> list[dict]:
    return _load()


def create_alert(symbol: str, field: str, condition: str, threshold: float, label: str = "") -> dict:
    alert = {
        "id": str(uuid.uuid4())[:8],
        "symbol": symbol,
        "field": field,
        "condition": condition,
        "threshold": threshold,
        "label": label or f"{symbol} {field} {condition} {threshold}",
        "active": True,
        "last_triggered": None,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    alerts = _load()
    alerts.append(alert)
    _save(alerts)
    return alert


def delete_alert(alert_id: str) -> bool:
    alerts = _load()
    new = [a for a in alerts if a["id"] != alert_id]
    if len(new) == len(alerts):
        return False
    _save(new)
    return True


def check_alerts(annotated: dict, synthesis: dict) -> list[dict]:
    """Evaluate all active alerts against current bundle. Returns triggered alerts."""
    alerts = _load()
    triggered = []
    now = datetime.now(tz=timezone.utc).isoformat()

    for alert in alerts:
        if not alert.get("active"):
            continue
        sym = alert["symbol"]
        df = annotated.get(sym)
        if df is None or df.empty:
            continue
        last = df.iloc[-1]
        synth = (synthesis or {}).get(sym, {})

        field = alert["field"]
        if field == "confluence_score":
            value = float(synth.get("confluence_score", 0) or 0)
        elif field in last.index:
            v = last.get(field)
            if v is None:
                continue
            value = float(v)
        else:
            continue

        cond = alert["condition"]
        thr = float(alert["threshold"])
        fired = (
            (cond == "above" and value > thr) or
            (cond == "below" and value < thr) or
            (cond == "crosses_above" and value > thr) or
            (cond == "crosses_below" and value < thr)
        )
        if fired:
            alert["last_triggered"] = now
            triggered.append({**alert, "current_value": round(value, 2)})

    _save(alerts)
    return triggered
