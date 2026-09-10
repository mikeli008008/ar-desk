"""Naive GEX：用 QQQ 期权链算 dealer gamma 分布，再按比例映射到 NQ 价格轴。

用途是判断**波动环境**（压波动 / 放波动），不是方向信号。
如果你已有 mikeli008008/gex 的输出，把 config 里 gex.source 改成 file 即可直接读。
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone

import numpy as np
import yfinance as yf

SQRT2PI = math.sqrt(2 * math.pi)


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT2PI


def bs_gamma(S: float, K: float, T: float, iv: float, r: float = 0.045) -> float:
    if T <= 0 or iv <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
    return _norm_pdf(d1) / (S * iv * math.sqrt(T))


def naive_gex(ticker: str = "QQQ", max_expiries: int = 6) -> dict:
    tk = yf.Ticker(ticker)
    spot = float(tk.fast_info["last_price"])
    now = datetime.now(timezone.utc)
    strikes: dict[float, float] = {}

    for exp in tk.options[:max_expiries]:
        T = max((datetime.fromisoformat(exp).replace(tzinfo=timezone.utc) - now).days, 0) / 365.0
        T = max(T, 1 / 365.0)
        try:
            chain = tk.option_chain(exp)
        except Exception:
            time.sleep(1.5)
            continue
        time.sleep(0.4)  # 避免被限流导致链数据残缺
        for df, sign in ((chain.calls, 1.0), (chain.puts, -1.0)):
            for _, row in df.iterrows():
                K = float(row["strike"])
                if abs(K / spot - 1) > 0.15:
                    continue
                oi = float(row.get("openInterest") or 0)
                iv = float(row.get("impliedVolatility") or 0)
                if oi <= 0 or iv <= 0:
                    continue
                g = bs_gamma(spot, K, T, iv)
                # naive: 假设 dealer 多 call、空 put
                notional = sign * g * oi * 100 * spot * spot * 0.01
                strikes[K] = strikes.get(K, 0.0) + notional

    if len(strikes) < 8:
        raise RuntimeError(f"期权链数据过稀（{len(strikes)} 个行权价），GEX 不可信")

    ks = np.array(sorted(strikes))
    vs = np.array([strikes[k] for k in ks])
    total = float(vs.sum())

    # 惯例：call wall 在现价上方找最大正 gamma，put wall 在现价下方找最负 gamma
    above = ks >= spot
    below = ks <= spot
    call_wall = float(ks[above][int(np.argmax(vs[above]))]) if above.any() else float(ks[int(np.argmax(vs))])
    put_wall = float(ks[below][int(np.argmin(vs[below]))]) if below.any() else float(ks[int(np.argmin(vs))])

    # gamma flip：累计 GEX 由负转正的行权价
    cum = np.cumsum(vs)
    flip = None
    for i in range(1, len(cum)):
        if cum[i - 1] < 0 <= cum[i]:
            flip = float(ks[i])
            break
    if flip is None:
        # 全区间同号：没有翻转点，标记为 None（环境由 net_gex 符号决定）
        flip = None

    degraded = not (above.any() and below.any())

    return {
        "degraded": degraded,
        "asof": now.isoformat(timespec="seconds"),
        "proxy": ticker,
        "proxy_spot": spot,
        "net_gex": total,
        "regime": "positive" if total > 0 else "negative",
        "call_wall_proxy": None if degraded else call_wall,
        "put_wall_proxy": None if degraded else put_wall,
        "gamma_flip_proxy": None if degraded else flip,
    }


def map_to_futures(gx: dict, nq_price: float) -> dict:
    """QQQ 行权价 → NQ 价格轴（按现价比例换算）。"""
    ratio = nq_price / gx["proxy_spot"]
    out = dict(gx)
    out["ratio"] = ratio
    if gx.get("degraded"):
        out["note"] = "期权链单边缺失（多为盘后/0DTE 数据稀疏），只用净 GEX 符号判断环境，不给墙位"
    for src, dst in (("call_wall_proxy", "call_wall"),
                     ("put_wall_proxy", "put_wall"),
                     ("gamma_flip_proxy", "gamma_flip")):
        out[dst] = round(gx[src] * ratio, 2) if gx.get(src) is not None else None
    return out


def load(cfg: dict, nq_price: float) -> dict:
    src = cfg["gex"].get("source", "yfinance")
    if src == "file":
        path = cfg["gex"]["file_path"]
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    try:
        return map_to_futures(naive_gex(cfg["symbol"]["proxy_etf"]), nq_price)
    except Exception as e:  # GEX 不可用时不阻断简报
        return {"regime": "unknown", "error": str(e)}
