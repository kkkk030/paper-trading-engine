#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.engine import run_once, fetch_upbit_prices
from src.paper import PaperBroker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["entry", "risk"], default="entry")
    args = parser.parse_args()

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

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "prices": prices,
        "signals": [s.__dict__ for s in signals],
        "alerts": alerts,
        "state": broker.state,
    }
    (ROOT / "reports" / "latest_cycle.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"mode={args.mode} alerts={len(alerts)} equity={broker.state['equity']:.0f} pos={len(broker.state['positions'])}")
    for a in alerts:
        print(a)


if __name__ == "__main__":
    main()
