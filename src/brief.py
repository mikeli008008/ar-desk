"""把引擎输出渲染成人看得懂的盘前简报。"""
from __future__ import annotations

from .engine import DAY_TYPES

BADGE = {"GO": "✅ 可做", "REDUCED": "⚠️ 减半仓", "NO-TRADE": "⛔️ 今日不做"}


def render(ctx: dict) -> str:
    d, s, gx = ctx["day"], ctx["sessions"], ctx["gex"]
    L = []
    L.append(f"# AR-Desk 盘前简报 · {ctx['date']}")
    L.append(f"**结论：{BADGE[ctx['verdict']]}**"
             + (f" — 未通过：{', '.join(ctx['fails'])}" if ctx["fails"] else ""))
    L.append("")

    L.append("## 1. 三段结构")
    if s.get("asia"):
        a = s["asia"]
        L.append(f"- 亚洲盘（建区间）：{a['low']:.2f} – {a['high']:.2f}｜中点 {a['mid']:.2f}｜宽度 {a['range']:.1f} 点")
    if s.get("london"):
        l = s["london"]
        L.append(f"- 伦敦盘（试探）：{l['low']:.2f} – {l['high']:.2f}｜收 {l['close']:.2f}"
                 f"｜高点 {l['high_time']} / 低点 {l['low_time']}")
    L.append(f"- 纽约盘（解决）：09:30–11:00 交易窗口，11:00 硬性收工")
    L.append("")

    L.append("## 2. 日型分类")
    L.append(f"**{d['type']}** — {DAY_TYPES.get(d['type'], '')}")
    L.append(f"- 依据：{d['why']}")
    L.append(f"- 方向偏好：{d['bias'] or '无（方向不明）'}")
    L.append("")

    L.append("## 3. 波动环境 (GEX)")
    if gx.get("regime") in ("positive", "negative"):
        L.append(f"- 净 GEX：{gx['regime']}（{gx.get('net_gex', 0):,.0f}）")
        L.append(f"- Call Wall {gx.get('call_wall')}｜Put Wall {gx.get('put_wall')}｜Gamma Flip {gx.get('gamma_flip')}")
        L.append(f"- 含义：{ctx['gex_note']}")
    else:
        L.append(f"- 不可用（{gx.get('error', 'n/a')}），按中性处理")
    L.append("")

    L.append("## 4. 入场区（价格不进这个区，就没有任何操作）")
    z = ctx["zone"]
    if z:
        L.append(f"- 参考腿：{z['leg_low']} → {z['leg_high']}")
        L.append(f"- {'折价区' if z['bias']=='long' else '溢价区'}：**{z['zone_low']} – {z['zone_high']}**")
        L.append(f"- 失效线（0.886）：**{z['invalidation']}** — 穿过即作废")
        L.append(f"- {z['note']}")
    else:
        L.append("- 无有效入场区（方向不明或试探腿缺失）")
    L.append("")

    L.append("## 5. 目标位阶梯（固定优先级，最近的先成为目标）")
    if ctx["ladder"]:
        for i, t in enumerate(ctx["ladder"], 1):
            L.append(f"{i}. **{t['price']}** — {t['label']}（距现价 {t['distance']} 点）")
    else:
        L.append("- 无（方向未定）")
    L.append("")

    L.append("## 6. 仓位")
    p = ctx.get("position")
    if p and p["contracts"] > 0:
        L.append(f"- {p['instrument']} × **{p['contracts']}** 手｜止损 {p['stop_points']} 点"
                 f"｜单笔风险 ${p['risk_dollars']}")
        L.append(f"- {p['note']}")
    elif p:
        L.append(f"- {p['note']}")
    else:
        L.append("- 不适用")
    L.append("")

    L.append("## 7. 检查清单（每一项都是“不做”条件）")
    for g in ctx["gates"]:
        L.append(f"- {'✅' if g['pass'] else '❌'} {g['gate']}：{g['note']}")
    L.append("")

    L.append("## 8. 收工规则")
    r = ctx["cfg"]["risk"]
    L.append(f"- 连亏 {r['max_consecutive_losses']} 笔 → 关电脑")
    L.append(f"- 当日亏损 {r['max_daily_loss_pct']}% → 关电脑")
    L.append(f"- 11:00 ET → 关电脑")
    L.append(f"- 晨间目标打到 → 关电脑")
    L.append(f"- 当前风控状态：{ctx['risk_state']['reason']}"
             f"（今日 {ctx['risk_state']['trades']} 笔 / {ctx['risk_state']['day_R']:+.2f}R）")
    L.append("")
    L.append("---")
    L.append("*本简报只做上下文与纪律约束，不构成投资建议。入场那一下的订单流确认仍然是你的判断。*")
    return "\n".join(L)
