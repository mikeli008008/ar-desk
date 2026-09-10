"""行情数据层：拉取期货 K 线并按美东时段切片。"""
from __future__ import annotations

from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ET = ZoneInfo("America/New_York")


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep]


def get_bars(symbol: str = "NQ=F", interval: str = "5m", period: str = "10d") -> pd.DataFrame:
    """返回带美东时区索引的 OHLCV。5m 最多 60 天，1m 最多 7 天。"""
    df = yf.download(symbol, period=period, interval=interval,
                     progress=False, auto_adjust=False)
    if df is None or df.empty:
        raise RuntimeError(f"无法获取 {symbol} {interval} 数据")
    df = _flatten(df)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(ET)
    return df.dropna()


def get_daily(symbol: str = "NQ=F", period: str = "3mo") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval="1d",
                     progress=False, auto_adjust=False)
    return _flatten(df).dropna()


def atr(daily: pd.DataFrame, n: int = 20) -> float:
    h, l, c = daily["high"], daily["low"], daily["close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return float(tr.tail(n).mean())


def _at(day: datetime, hhmm: str) -> datetime:
    hh, mm = [int(x) for x in hhmm.split(":")]
    return datetime.combine(day.date(), dtime(hh, mm), tzinfo=ET)


def session_window(today: datetime, start_hhmm: str, end_hhmm: str,
                   start_prev_day: bool = False) -> tuple[datetime, datetime]:
    start_day = today - timedelta(days=1) if start_prev_day else today
    start = _at(start_day, start_hhmm)
    end = _at(today, end_hhmm)
    # 周一的亚洲盘从周日 18:00 globex 开盘算起
    if start_prev_day and start.weekday() == 5:  # 周六无盘
        start = start - timedelta(days=1)
    return start, end


def slice_session(bars: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    return bars[(bars.index >= start) & (bars.index < end)]


def session_stats(seg: pd.DataFrame) -> dict | None:
    if seg.empty:
        return None
    return {
        "high": float(seg["high"].max()),
        "low": float(seg["low"].min()),
        "mid": float((seg["high"].max() + seg["low"].min()) / 2),
        "open": float(seg["open"].iloc[0]),
        "close": float(seg["close"].iloc[-1]),
        "range": float(seg["high"].max() - seg["low"].min()),
        "volume": float(seg["volume"].sum()),
        "high_time": seg["high"].idxmax().strftime("%H:%M"),
        "low_time": seg["low"].idxmin().strftime("%H:%M"),
    }


def swing_points(bars: pd.DataFrame, left: int = 2, right: int = 2) -> tuple[list, list]:
    """分形摆动高/低点，返回 (highs, lows) 价格列表，按时间倒序。"""
    highs, lows = [], []
    h, l = bars["high"].values, bars["low"].values
    for i in range(left, len(bars) - right):
        win_h = h[i - left:i + right + 1]
        win_l = l[i - left:i + right + 1]
        if h[i] == win_h.max() and (win_h == h[i]).sum() == 1:
            highs.append(float(h[i]))
        if l[i] == win_l.min() and (win_l == l[i]).sum() == 1:
            lows.append(float(l[i]))
    return highs[::-1], lows[::-1]
