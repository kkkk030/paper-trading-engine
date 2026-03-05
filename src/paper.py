from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Position:
    symbol: str
    qty: float
    entry: float
    stop: float
    r_value: float
    tp1_done: bool = False
    tp2_done: bool = False
    high: float = 0.0


class PaperBroker:
    def __init__(self, cfg: dict, state_path: Path, trades_path: Path):
        self.cfg = cfg
        self.state_path = state_path
        self.trades_path = trades_path
        self.state = self._load_state()

    def _today(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_state(self):
        capital = float(self.cfg["capital"])
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            state.setdefault("fee_total", 0.0)
            state.setdefault("daily", {})
            state["daily"].setdefault("date", self._today())
            state["daily"].setdefault("start_equity", state.get("equity", capital))
            state["daily"].setdefault("realized", 0.0)
            state["daily"].setdefault("fees", 0.0)
            state.setdefault("positions", {})
            state.setdefault("cooldowns", {})
            return state
        return {
            "equity": capital,
            "cash": capital,
            "positions": {},
            "cooldowns": {},
            "fee_total": 0.0,
            "daily": {"date": self._today(), "start_equity": capital, "realized": 0.0, "fees": 0.0},
        }

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2))

    def _log_trade(self, event: dict):
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trades_path.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _roll_daily_if_needed(self):
        today = self._today()
        if self.state["daily"]["date"] != today:
            self.state["daily"] = {
                "date": today,
                "start_equity": self.state["equity"],
                "realized": 0.0,
                "fees": 0.0,
            }

    def _daily_loss_hit(self):
        d = self.state["daily"]
        if d["start_equity"] <= 0:
            return False
        pnl_pct = d["realized"] / d["start_equity"]
        return pnl_pct <= float(self.cfg["daily_loss_limit"])

    def _fee_rate(self) -> float:
        return float(self.cfg.get("fee_rate", 0.0005))

    def _apply_fee(self, notional: float) -> float:
        fee = notional * self._fee_rate()
        self.state["fee_total"] += fee
        self.state["daily"]["fees"] += fee
        return fee

    def _mark_to_market(self, prices: dict[str, float]):
        mtm = self.state["cash"]
        for sym, p in self.state["positions"].items():
            mtm += p["qty"] * prices.get(sym, p["entry"])
        self.state["equity"] = mtm

    def process(self, signals: list, prices: dict[str, float], allow_entries: bool = True) -> list[str]:
        self._roll_daily_if_needed()
        alerts: list[str] = []

        # position management first
        for sym, raw in list(self.state["positions"].items()):
            if sym not in prices:
                continue
            pos = Position(**raw)
            px = prices[sym]
            pos.high = max(pos.high or pos.entry, px)

            # stop loss
            if px <= pos.stop:
                notional = px * pos.qty
                fee = self._apply_fee(notional)
                pnl = (px - pos.entry) * pos.qty - fee
                self.state["cash"] += notional - fee
                self.state["daily"]["realized"] += pnl
                self._log_trade({"ts": datetime.now(timezone.utc).isoformat(), "symbol": sym, "side": "SELL", "kind": "STOP", "qty": pos.qty, "price": px, "fee": fee, "pnl": pnl})
                alerts.append(f"[체결] {sym} STOP SELL qty={pos.qty:.6f} @ {px:,.0f} pnl={pnl:,.0f} fee={fee:,.0f}")
                self.state["cooldowns"][sym] = datetime.now(timezone.utc).timestamp()
                del self.state["positions"][sym]
                continue

            # tp1
            tp1 = pos.entry + pos.r_value * float(self.cfg["take_profit"]["tp1_r"])
            if (not pos.tp1_done) and px >= tp1:
                q = pos.qty * float(self.cfg["take_profit"]["tp1_size"])
                notional = px * q
                fee = self._apply_fee(notional)
                pnl = (px - pos.entry) * q - fee
                pos.qty -= q
                pos.tp1_done = True
                pos.stop = max(pos.stop, pos.entry)  # breakeven
                self.state["cash"] += notional - fee
                self.state["daily"]["realized"] += pnl
                self._log_trade({"ts": datetime.now(timezone.utc).isoformat(), "symbol": sym, "side": "SELL", "kind": "TP1", "qty": q, "price": px, "fee": fee, "pnl": pnl})
                alerts.append(f"[체결] {sym} TP1 SELL qty={q:.6f} @ {px:,.0f} pnl={pnl:,.0f} fee={fee:,.0f}")

            # tp2
            tp2 = pos.entry + pos.r_value * float(self.cfg["take_profit"]["tp2_r"])
            if (not pos.tp2_done) and px >= tp2:
                q = pos.qty * (float(self.cfg["take_profit"]["tp2_size"]) / (1.0 - float(self.cfg["take_profit"]["tp1_size"])))
                notional = px * q
                fee = self._apply_fee(notional)
                pnl = (px - pos.entry) * q - fee
                pos.qty -= q
                pos.tp2_done = True
                self.state["cash"] += notional - fee
                self.state["daily"]["realized"] += pnl
                self._log_trade({"ts": datetime.now(timezone.utc).isoformat(), "symbol": sym, "side": "SELL", "kind": "TP2", "qty": q, "price": px, "fee": fee, "pnl": pnl})
                alerts.append(f"[체결] {sym} TP2 SELL qty={q:.6f} @ {px:,.0f} pnl={pnl:,.0f} fee={fee:,.0f}")

            # trailing runner after tp2
            if pos.tp2_done:
                trail_pct = 0.12
                tstop = pos.high * (1 - trail_pct)
                pos.stop = max(pos.stop, tstop)

            self.state["positions"][sym] = asdict(pos)

        # entries
        if allow_entries and (not self._daily_loss_hit()):
            max_pos = int(self.cfg["max_positions"])
            for s in signals:
                if len(self.state["positions"]) >= max_pos:
                    break
                if s.action != "BUY":
                    continue
                if s.symbol in self.state["positions"]:
                    continue

                cd = self.state["cooldowns"].get(s.symbol)
                if cd:
                    cool_m = int(self.cfg["reentry_cooldown_minutes"])
                    if datetime.now(timezone.utc).timestamp() - cd < cool_m * 60:
                        continue

                px = prices.get(s.symbol)
                if not px:
                    continue

                risk_amt = self.state["equity"] * float(self.cfg["risk_per_trade"])
                stop_pct = 0.03
                risk_per_unit = px * stop_pct
                qty = risk_amt / risk_per_unit if risk_per_unit > 0 else 0

                # cash cap by available slots (fee included)
                slots_left = max(1, max_pos - len(self.state["positions"]))
                fee_rate = self._fee_rate()
                max_notional = self.state["cash"] / (slots_left * (1 + fee_rate))
                notional = qty * px
                if notional > max_notional:
                    qty = max_notional / px
                    notional = max_notional

                if qty <= 0 or notional < 5000:
                    continue

                fee = self._apply_fee(notional)
                self.state["cash"] -= (notional + fee)
                self.state["daily"]["realized"] -= fee
                pos = Position(symbol=s.symbol, qty=qty, entry=px, stop=px * (1 - stop_pct), r_value=px * stop_pct, high=px)
                self.state["positions"][s.symbol] = asdict(pos)
                self._log_trade({"ts": datetime.now(timezone.utc).isoformat(), "symbol": s.symbol, "side": "BUY", "kind": "ENTRY", "qty": qty, "price": px, "fee": fee, "score": s.score, "regime": s.regime})
                alerts.append(f"[체결] {s.symbol} BUY qty={qty:.6f} @ {px:,.0f} score={s.score} fee={fee:,.0f}")

        self._mark_to_market(prices)
        self._save_state()
        return alerts
