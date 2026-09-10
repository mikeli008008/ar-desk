"""交易日志 + 推送。计划先落盘，收盘后回填结果，用来验证每个 gate 到底有没有用。"""
from __future__ import annotations

import csv
import os
from collections import defaultdict

import requests

FIELDS = ["date", "day_type", "bias", "verdict", "fails", "zone_low", "zone_high",
          "invalidation", "target1", "target1_label", "contracts",
          "taken", "result", "R", "notes"]


def log_plan(path: str, ctx: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    exists = os.path.exists(path)
    z = ctx.get("zone") or {}
    t1 = (ctx["ladder"] or [{}])[0]
    row = {
        "date": ctx["date"], "day_type": ctx["day"]["type"], "bias": ctx["day"]["bias"] or "",
        "verdict": ctx["verdict"], "fails": "|".join(ctx["fails"]),
        "zone_low": z.get("zone_low", ""), "zone_high": z.get("zone_high", ""),
        "invalidation": z.get("invalidation", ""),
        "target1": t1.get("price", ""), "target1_label": t1.get("label", ""),
        "contracts": (ctx.get("position") or {}).get("contracts", ""),
        "taken": "", "result": "", "R": "", "notes": "",
    }
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


def stats(path: str) -> str:
    """按日型统计胜率与期望，跑满 30–40 笔后才有参考意义。"""
    if not os.path.exists(path):
        return "暂无历史记录"
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("R")]
    if not rows:
        return "暂无已回填结果的记录"

    agg = defaultdict(lambda: {"n": 0, "wins": 0, "R": 0.0})
    for r in rows:
        try:
            R = float(r["R"])
        except ValueError:
            continue
        k = r["day_type"]
        agg[k]["n"] += 1
        agg[k]["wins"] += 1 if R > 0 else 0
        agg[k]["R"] += R

    lines = ["日型 | 笔数 | 胜率 | 累计R | 每笔期望"]
    for k, v in sorted(agg.items(), key=lambda x: -x[1]["n"]):
        lines.append(f"{k} | {v['n']} | {v['wins']/v['n']:.0%} | {v['R']:+.2f} | {v['R']/v['n']:+.2f}")
    return "\n".join(lines)


def telegram(text: str) -> bool:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text[:4000],
                                "parse_mode": "Markdown"}, timeout=20)
        return r.ok
    except Exception:
        return False
