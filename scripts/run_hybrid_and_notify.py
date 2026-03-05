#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.engine import run_once, fetch_upbit_prices
from src.paper import PaperBroker


def send_event(text: str):
    try:
        subprocess.run([
            "openclaw", "system", "event",
            "--text", text,
            "--mode", "now",
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["entry", "risk"], default="entry")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--summary", action="store_true")
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

    recent_trades = load_recent_trades(ROOT / "logs" / "trades.jsonl", limit=20)
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "prices": prices,
        "signals": [s.__dict__ for s in signals],
        "alerts": alerts,
        "state": broker.state,
        "recentTrades": recent_trades,
    }
    latest_json = json.dumps(report, ensure_ascii=False, indent=2)
    (ROOT / "reports" / "latest_cycle.json").write_text(latest_json)
    # GitHub Pages docs mirror
    (ROOT / "docs" / "latest_cycle.json").write_text(latest_json)

    if args.notify and alerts:
        text = "\n".join(["[Paper] 체결 이벤트"] + alerts[:8])
        send_event(text)

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
