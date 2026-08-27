from __future__ import annotations

import json
import statistics
import time
import urllib.error
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
    gate_pass: int = 0
    gate_need: int = 0
    atr_pct: float = 0.0


def _get_json(url: str, retries: int = 3, backoff: float = 0.8):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise last_err


def fetch_upbit_ohlcv(symbol: str, unit: int = 15, count: int = 120):
    url = f"https://api.upbit.com/v1/candles/minutes/{unit}?market={symbol}&count={count}"
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
        score -= 4
    elif regime == "SHOCK":
        score -= 12

    score = max(0.0, min(100.0, score))
    reason = f"ret5={ret_5:+.2f}% ret20={ret_20:+.2f}% volx={v_ratio:.2f} regime={regime}"
    return score, reason


def atr_pct(rows: list[dict], period: int = 14) -> float:
    if len(rows) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(-period, 0):
        row = rows[i]
        prev_close = float(rows[i - 1]["trade_price"])
        high = float(row.get("high_price", row["trade_price"]))
        low = float(row.get("low_price", row["trade_price"]))
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    close = float(rows[-1]["trade_price"])
    return (sum(trs) / len(trs) / close * 100) if close else 0.0


def decide(score: float, regime: str, entry_threshold: float = 70.0, gate_pass: int = 0, gate_need: int = 0, rr_ok: bool = True) -> str:
    if regime == "SHOCK":
        return "HOLD"
    if score >= entry_threshold and gate_pass >= gate_need and rr_ok:
        return "BUY"
    if score <= 35:
        return "EXIT"
    return "HOLD"


def run_once(config_path: Path) -> list[Signal]:
    cfg = json.loads(config_path.read_text())
    out: list[Signal] = []

    symbols = cfg["symbols"]
    by_regime = cfg.get("entry_score_threshold_by_regime", {})
    default_threshold = float(cfg.get("entry_score_threshold", 70))
    gate_need = int(cfg.get("entry_gate_min_pass", 2))
    min_rr_tp1 = float(cfg.get("min_rr_tp1", 1.2))
    tp1_r = float(cfg.get("take_profit", {}).get("tp1_r", 1.8))

    rows15: dict[str, list[dict]] = {s: fetch_upbit_ohlcv(s, unit=15, count=120) for s in symbols}
    rows60: dict[str, list[dict]] = {s: fetch_upbit_ohlcv(s, unit=60, count=120) for s in symbols}
    rows5: dict[str, list[dict]] = {s: fetch_upbit_ohlcv(s, unit=5, count=80) for s in symbols}

    btc_rows = rows15.get("KRW-BTC", [])
    btc_closes = [r["trade_price"] for r in btc_rows]
    btc_ret20 = (btc_closes[-1] / btc_closes[-21] - 1) * 100 if len(btc_closes) >= 21 else 0.0
    btc_regime = classify_regime(btc_closes)

    for symbol in symbols:
        rows = rows15[symbol]
        closes = [r["trade_price"] for r in rows]
        volumes = [r["candle_acc_trade_volume"] for r in rows]
        regime = classify_regime(closes)
        score, reason = score_symbol(closes, volumes, regime)

        th = float(by_regime.get(regime, default_threshold))

        # gate #1: 1h trend
        c60 = [r["trade_price"] for r in rows60[symbol]]
        ma20_60 = sum(c60[-20:]) / 20 if len(c60) >= 20 else c60[-1] if c60 else 0
        ma60_60 = sum(c60[-60:]) / 60 if len(c60) >= 60 else ma20_60
        gate_trend = ma20_60 >= ma60_60

        # gate #2: 15m volume expansion
        v20 = (sum(volumes[-20:]) / 20) if len(volumes) >= 20 else (sum(volumes) / max(1, len(volumes)))
        gate_volume = volumes[-1] > v20 if volumes else False

        # gate #3: relative strength vs BTC (except BTC itself)
        ret20 = (closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 else 0.0
        gate_rel = True if symbol == "KRW-BTC" else (ret20 >= btc_ret20)

        # gate #4: 5m timing. Avoid buying while short timing is still below its mean.
        c5 = [r["trade_price"] for r in rows5[symbol]]
        ma20_5 = sum(c5[-20:]) / 20 if len(c5) >= 20 else c5[-1] if c5 else 0
        gate_timing = bool(c5 and c5[-1] >= ma20_5)

        # gate policy: higher timeframe trend plus at least one participation check and timing.
        gate_core_ok = gate_trend and (gate_volume or gate_rel) and gate_timing
        # DOWN 레짐에서는 상대강도(Gate3) 필수
        if regime == "DOWN":
            gate_core_ok = gate_core_ok and gate_rel
        # Do not open new risk while BTC itself is in shock.
        if btc_regime == "SHOCK" and symbol != "KRW-BTC":
            gate_core_ok = False

        gates = [gate_trend, gate_volume, gate_rel, gate_timing]
        gate_pass = sum(1 for g in gates if g)

        atr = atr_pct(rows)
        rr_ok = tp1_r >= min_rr_tp1
        action = decide(score, regime, entry_threshold=th, gate_pass=(1 if gate_core_ok else 0), gate_need=1, rr_ok=rr_ok)

        gate_txt = (
            f"gate={gate_pass}/4 core={'Y' if gate_core_ok else 'N'} "
            f"trend60={'Y' if gate_trend else 'N'} vol15={'Y' if gate_volume else 'N'} "
            f"relBTC={'Y' if gate_rel else 'N'} timing5={'Y' if gate_timing else 'N'} "
            f"btcRegime={btc_regime} atr={atr:.2f}% rr={'Y' if rr_ok else 'N'}"
        )
        out.append(Signal(symbol=symbol, score=round(score, 1), regime=regime, action=action, reason=f"{reason} | th={th} {gate_txt}", gate_pass=gate_pass, gate_need=1, atr_pct=round(atr, 3)))
    return out


def save_snapshot(signals: list[Signal], out_path: Path):
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "signals": [s.__dict__ for s in signals],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
