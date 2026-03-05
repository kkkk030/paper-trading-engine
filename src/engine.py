from __future__ import annotations

import json
import statistics
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Signal:
    symbol: str
    score: float
    regime: str
    action: str
    reason: str


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_upbit_ohlcv(symbol: str, count: int = 120):
    url = f"https://api.upbit.com/v1/candles/minutes/15?market={symbol}&count={count}"
    rows = _get_json(url)
    rows.reverse()
    return rows


def fetch_upbit_prices(symbols: list[str]) -> dict[str, float]:
    mkts = ",".join(symbols)
    rows = _get_json(f"https://api.upbit.com/v1/ticker?markets={mkts}")
    return {r["market"]: float(r["trade_price"]) for r in rows}


def classify_regime(closes: list[float]) -> str:
    if len(closes) < 60:
        return "RANGE"
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    vol = statistics.pstdev(closes[-20:]) / ma20 if ma20 else 0
    if vol > 0.04:
        return "SHOCK"
    if ma20 > ma60:
        return "UP"
    if ma20 < ma60:
        return "DOWN"
    return "RANGE"


def score_symbol(closes: list[float], volumes: list[float], regime: str) -> tuple[float, str]:
    if len(closes) < 30:
        return 0.0, "insufficient data"
    ret_5 = (closes[-1] / closes[-6] - 1) * 100
    ret_20 = (closes[-1] / closes[-21] - 1) * 100
    v_ratio = volumes[-1] / (sum(volumes[-20:]) / 20) if sum(volumes[-20:]) else 1

    score = 50.0
    score += max(-15, min(15, ret_5 * 2.0))
    score += max(-20, min(20, ret_20 * 1.2))
    score += max(-10, min(10, (v_ratio - 1) * 12))

    if regime == "UP":
        score += 8
    elif regime == "DOWN":
        score -= 8
    elif regime == "SHOCK":
        score -= 12

    score = max(0.0, min(100.0, score))
    reason = f"ret5={ret_5:+.2f}% ret20={ret_20:+.2f}% volx={v_ratio:.2f} regime={regime}"
    return score, reason


def decide(score: float, regime: str) -> str:
    if regime == "SHOCK":
        return "HOLD"
    if score >= 70:
        return "BUY"
    if score <= 35:
        return "EXIT"
    return "HOLD"


def run_once(config_path: Path) -> list[Signal]:
    cfg = json.loads(config_path.read_text())
    out: list[Signal] = []
    for symbol in cfg["symbols"]:
        rows = fetch_upbit_ohlcv(symbol)
        closes = [r["trade_price"] for r in rows]
        volumes = [r["candle_acc_trade_volume"] for r in rows]
        regime = classify_regime(closes)
        score, reason = score_symbol(closes, volumes, regime)
        action = decide(score, regime)
        out.append(Signal(symbol=symbol, score=round(score, 1), regime=regime, action=action, reason=reason))
    return out


def save_snapshot(signals: list[Signal], out_path: Path):
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "signals": [s.__dict__ for s in signals],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
