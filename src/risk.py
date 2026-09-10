"""风控状态机 —— 系统里唯一有权直接说“今天不做”的模块。

规则来源：连亏 2 笔停、当日亏损额停、11:00 停、晨间目标打到也停、
亏损单不加仓、止损只朝有利方向移动（永不放宽）。
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def read_state(journal_path: str, today: str, cfg: dict) -> dict:
    """从日志读当天已发生的情况，决定还能不能开新仓。"""
    r = cfg["risk"]
    state = {"trades": 0, "consecutive_losses": 0, "day_R": 0.0,
             "allowed": True, "reason": "正常"}
    if not os.path.exists(journal_path):
        return state

    with open(journal_path, newline="", encoding="utf-8") as f:
        rows = [x for x in csv.DictReader(f) if x.get("date") == today and x.get("result")]

    streak = 0
    for row in rows:
        try:
            R = float(row.get("R") or 0)
        except ValueError:
            R = 0.0
        state["day_R"] += R
        state["trades"] += 1
        streak = streak + 1 if R < 0 else 0
    state["consecutive_losses"] = streak

    max_loss_R = r["max_daily_loss_pct"] / r["risk_per_trade_pct"]
    if streak >= r["max_consecutive_losses"]:
        state.update(allowed=False, reason=f"连亏 {streak} 笔 → 当日收工")
    elif state["day_R"] <= -max_loss_R:
        state.update(allowed=False, reason=f"当日亏损达上限 {state['day_R']:.2f}R → 收工")
    elif state["trades"] >= r["max_trades_per_day"]:
        state.update(allowed=False, reason=f"已交易 {state['trades']} 笔，达当日上限")

    now = datetime.now(ET)
    if now.strftime("%H:%M") >= cfg["sessions"]["ny_hard_stop"]:
        state.update(allowed=False, reason=f"已过 {cfg['sessions']['ny_hard_stop']} 硬性收工时间")

    return state


def size_position(entry: float, stop: float, cfg: dict, instrument: str = "MNQ") -> dict:
    r = cfg["risk"]
    pv = cfg["symbol"]["point_value_mnq"] if instrument == "MNQ" else cfg["symbol"]["point_value_nq"]
    risk_dollars = r["account_size"] * r["risk_per_trade_pct"] / 100
    stop_points = abs(entry - stop)
    if stop_points <= 0:
        return {"contracts": 0, "note": "止损距离为 0，无法计算"}
    per_contract = stop_points * pv
    contracts = int(risk_dollars // per_contract)
    return {
        "instrument": instrument,
        "risk_dollars": round(risk_dollars, 2),
        "stop_points": round(stop_points, 2),
        "risk_per_contract": round(per_contract, 2),
        "contracts": max(contracts, 0),
        "note": "亏损单不加仓；止损只朝有利方向移动，永不放宽" if contracts > 0
                else "按当前止损距离，单笔风险已超预算 → 不做或换更近的失效点",
    }
