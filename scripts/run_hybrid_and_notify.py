#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.engine import run_once, fetch_upbit_prices
from src.paper import PaperBroker


def send_event(text: str):
    try:
        subprocess.run([
            "openclaw", "message", "send",
            "--channel", "telegram",
            "--target", "6411344447",
            "--message", text,
        ], check=False)
    except Exception:
        pass


def load_recent_trades(path: Path, limit: int = 20):
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def publish_docs_snapshot(mode: str):
    try:
        subprocess.run(["git", "add", "docs/latest_cycle.json"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"chore: publish {mode} cycle snapshot"], cwd=ROOT, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=False)
    except Exception:
        pass


def _parse_reason_flags(reason: str) -> dict:
    text = reason or ""
    m = re.search(r"gate=(\d+)/(\d+)", text)
    gate_pass = int(m.group(1)) if m else 0
    trend = "trend60=Y" in text
    vol = "vol15=Y" in text
    rel = "relBTC=Y" in text
    core = "core=Y" in text
    return {"gate_pass": gate_pass, "trend": trend, "vol": vol, "rel": rel, "core": core}


def _shadow_action(signal) -> str:
    # 섀넌 보완형 실험용: 현재 강화 정책 기반(하드스탑 포함)
    f = _parse_reason_flags(getattr(signal, "reason", ""))
    score = float(getattr(signal, "score", 0))
    regime = getattr(signal, "regime", "RANGE")
    if regime == "SHOCK":
        return "HOLD"

    th = {"UP": 55, "RANGE": 56, "DOWN": 62, "SHOCK": 100}.get(regime, 58)
    core_ok = f["core"] or (f["trend"] and (f["vol"] or f["rel"]))
    if regime == "DOWN":
        core_ok = core_ok and f["rel"]

    if score >= th and core_ok:
        return "BUY"
    if score <= 35:
        return "EXIT"
    return "HOLD"


def _seed_shadow_from_live_if_needed():
    live_path = ROOT / "data" / "paper_state.json"
    shadow_path = ROOT / "data" / "shadow_shannon_state.json"
    if shadow_path.exists() or (not live_path.exists()):
        return
    try:
        live = json.loads(live_path.read_text())
        shadow_path.write_text(json.dumps(live, ensure_ascii=False, indent=2))
    except Exception:
        pass


def _run_shadow(mode: str, cfg: dict, prices: dict, signals: list) -> dict:
    _seed_shadow_from_live_if_needed()

    cfg_shadow = dict(cfg)
    cfg_shadow["hard_stop_pct"] = float(cfg.get("hard_stop_pct", 0.04))

    s = PaperBroker(
        cfg=cfg_shadow,
        state_path=ROOT / "data" / "shadow_shannon_state.json",
        trades_path=ROOT / "logs" / "shadow_shannon_trades.jsonl",
    )

    if mode == "entry":
        sig_s = [
            SimpleNamespace(symbol=x.symbol, score=x.score, regime=x.regime, action=_shadow_action(x), reason=x.reason)
            for x in signals
        ]
    else:
        sig_s = []

    alerts_s = s.process(sig_s, prices, allow_entries=(mode == "entry"))

    snap = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "shadow": {
            "equity": s.state.get("equity", 0),
            "cash": s.state.get("cash", 0),
            "positions": len(s.state.get("positions", {})),
            "daily_realized": s.state.get("daily", {}).get("realized", 0),
            "alerts": len(alerts_s),
        },
    }
    (ROOT / "reports" / "shadow_compare_latest.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2))
    return snap


def _maybe_send_daily_compare(live_state: dict, shadow_snap: dict):
    now = datetime.now()
    if now.hour < 22:
        return

    marker = ROOT / "reports" / "shadow_daily_sent.txt"
    today = now.strftime("%Y-%m-%d")
    if marker.exists() and marker.read_text().strip() == today:
        return

    live_eq = float(live_state.get("equity", 0))
    live_real = float(live_state.get("daily", {}).get("realized", 0))
    sh = shadow_snap.get("shadow", {})
    sh_eq = float(sh.get("equity", 0))
    sh_real = float(sh.get("daily_realized", 0))

    diff = sh_eq - live_eq
    text = (
        f"[Shadow 비교/일1회] {today}\n"
        f"- Live Equity: {live_eq:,.0f}원 | 당일실현: {live_real:,.0f}원\n"
        f"- Shadow(섀넌보완) Equity: {sh_eq:,.0f}원 | 당일실현: {sh_real:,.0f}원\n"
        f"- 차이(Shadow-Live): {diff:+,.0f}원"
    )
    send_event(text)
    marker.write_text(today)


def _format_fill_message(mode: str, fills: list[dict], state: dict, signals: list) -> str:
    if not fills:
        return "[Paper] 체결 이벤트"

    lines = [f"[Paper 체결/{mode}] {datetime.now().strftime('%m-%d %H:%M:%S')}"]
    signal_by_symbol = {getattr(s, "symbol", ""): s for s in signals}

    for t in fills:
        symbol = t.get("symbol", "-")
        side = t.get("side", "-")
        kind = t.get("kind", "-")
        qty = float(t.get("qty", 0))
        price = float(t.get("price", 0))
        fee = float(t.get("fee", 0))
        notional = qty * price

        if side == "BUY":
            pos = state.get("positions", {}).get(symbol, {})
            avg = float(pos.get("entry", price))
            sig = signal_by_symbol.get(symbol)
            reason = getattr(sig, "reason", "entry signal") if sig else "entry signal"
            score = getattr(sig, "score", t.get("score", "-")) if sig else t.get("score", "-")
            lines += [
                f"- {symbol} {kind} {side}",
                f"  수량: {qty:.6f}",
                f"  매수금액: {notional:,.0f}원 @ {price:,.0f}원",
                f"  평단가: {avg:,.0f}원",
                f"  수수료: {fee:,.0f}원",
                f"  판단기준: score={score} | {reason}",
            ]
        else:
            pnl = float(t.get("pnl", 0))
            lines += [
                f"- {symbol} {kind} {side}",
                f"  수량: {qty:.6f}",
                f"  체결금액: {notional:,.0f}원 @ {price:,.0f}원",
                f"  실현손익: {pnl:,.0f}원",
                f"  수수료: {fee:,.0f}원",
                f"  판단기준: {kind} 조건 충족",
            ]

    lines.append(f"잔여 포지션: {len(state.get('positions', {}))}개 | Equity: {float(state.get('equity', 0)):,.0f}원")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["entry", "risk"], default="entry")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--summary", action="store_true")
    p.add_argument("--publish", action="store_true", help="docs/latest_cycle.json을 GitHub(main)로 푸시")
    args = p.parse_args()

    cfg_path = ROOT / "config" / "strategy_v1.json"
    cfg = json.loads(cfg_path.read_text())

    prices = fetch_upbit_prices(cfg["symbols"])
    signals = run_once(cfg_path) if args.mode == "entry" else []

    broker = PaperBroker(
        cfg=cfg,
        state_path=ROOT / "data" / "paper_state.json",
        trades_path=ROOT / "logs" / "trades.jsonl",
    )
    alerts = broker.process(signals, prices, allow_entries=(args.mode == "entry"))

    shadow = _run_shadow(args.mode, cfg, prices, signals)

    recent_trades = load_recent_trades(ROOT / "logs" / "trades.jsonl", limit=20)
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "prices": prices,
        "signals": [s.__dict__ for s in signals],
        "alerts": alerts,
        "state": broker.state,
        "recentTrades": recent_trades,
        "shadow": shadow,
        "riskControls": {
            "risk_per_trade": cfg.get("risk_per_trade"),
            "daily_loss_limit": cfg.get("daily_loss_limit"),
            "max_positions": cfg.get("max_positions"),
            "stop_confirm_bars": cfg.get("stop_confirm_bars"),
            "hard_stop_pct": cfg.get("hard_stop_pct"),
            "stop_atr_mult": cfg.get("stop_atr_mult"),
            "stop_pct_min": cfg.get("stop_pct_min"),
            "stop_pct_max": cfg.get("stop_pct_max"),
            "trailing_stop_pct": cfg.get("trailing_stop_pct"),
        },
    }
    latest_json = json.dumps(report, ensure_ascii=False, indent=2)
    (ROOT / "reports" / "latest_cycle.json").write_text(latest_json)
    (ROOT / "docs" / "latest_cycle.json").write_text(latest_json)

    if args.notify and alerts:
        fills = recent_trades[-len(alerts):] if recent_trades else []
        text = _format_fill_message(args.mode, fills, broker.state, signals)
        send_event(text)

    if args.mode == "risk":
        _maybe_send_daily_compare(broker.state, shadow)

    if args.publish:
        publish_docs_snapshot(args.mode)

    if args.summary:
        d = broker.state["daily"]
        pnl_pct = (d["realized"] / d["start_equity"] * 100) if d["start_equity"] else 0
        text = (
            f"[Paper 요약] equity={broker.state['equity']:,.0f} KRW | "
            f"daily={d['realized']:,.0f} KRW ({pnl_pct:+.2f}%) | "
            f"open_pos={len(broker.state['positions'])}"
        )
        send_event(text)

    print(f"mode={args.mode} alerts={len(alerts)} equity={broker.state['equity']:.0f} pos={len(broker.state['positions'])}")


if __name__ == "__main__":
    main()
