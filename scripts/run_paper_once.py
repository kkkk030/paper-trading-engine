#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.engine import run_once, save_snapshot
signals = run_once(ROOT / "config" / "strategy_v1.json")

for s in signals:
    print(f"[{s.symbol}] score={s.score} regime={s.regime} action={s.action} | {s.reason}")

save_snapshot(signals, ROOT / "reports" / "latest_signals.json")
print("saved -> reports/latest_signals.json")
