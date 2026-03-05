#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.engine import run_once, fetch_upbit_prices
from src.paper import PaperBroker


def main():
    cfg_path = ROOT / "config" / "strategy_v1.json"
    cfg = json.loads(cfg_path.read_text())

    signals = run_once(cfg_path)
    prices = fetch_upbit_prices(cfg["symbols"])

    broker = PaperBroker(
        cfg=cfg,
        state_path=ROOT / "data" / "paper_state.json",
        trades_path=ROOT / "logs" / "trades.jsonl",
    )
    alerts = broker.process(signals, prices)

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "prices": prices,
        "signals": [s.__dict__ for s in signals],
        "alerts": alerts,
        "state": broker.state,
    }
    out = ROOT / "reports" / "latest_cycle.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    for s in signals:
        print(f"[{s.symbol}] score={s.score} regime={s.regime} action={s.action}")

    if alerts:
        print("\n-- fills --")
        for a in alerts:
            print(a)
    else:
        print("\n(no fills this cycle)")

    d = broker.state["daily"]
    print(f"\nEQUITY={broker.state['equity']:,.0f} CASH={broker.state['cash']:,.0f} POS={len(broker.state['positions'])} D_REAL={d['realized']:,.0f}")
    print("saved -> reports/latest_cycle.json")


if __name__ == "__main__":
    main()
