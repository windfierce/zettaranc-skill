#!/usr/bin/env python3
"""
活跃市值（0AMV）数据加载与择时信号模块。

数据源：指南针 0AMV 活跃市值指数日线 CSV（date/open/high/low/close/volume/amount）。
规则（来自 zettaranc 体系）：
- 日环比 >= +4%   → 多头信号（增量资金进场）
- 日环比 <= -2.3% → 空头信号（资金离场）
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


@dataclass
class ActiveMarketValuePoint:
    """0AMV 活跃市值单日数据。"""

    date: str  # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    pct_chg: float = 0.0
    cum2_pct: float = 0.0  # 两日累计涨幅（今日 close / 前2个交易日 close - 1）
    signal: str = "NEUTRAL"  # UP / DOWN / NEUTRAL


def default_path() -> Path:
    """默认 CSV 路径。"""
    return Path(__file__).resolve().parent.parent / "data" / "0amv_active_market_value.csv"


def _finalize_points(raw_rows: list[dict]) -> list[ActiveMarketValuePoint]:
    """把原始 OHLCV 行转成 ActiveMarketValuePoint，并计算 pct/cum2/signal。"""
    points: list[ActiveMarketValuePoint] = []
    prev_close: float | None = None
    for row in raw_rows:
        close = float(row["close"])
        pct_chg = (close / prev_close - 1.0) * 100.0 if prev_close and prev_close > 0 else 0.0
        if pct_chg >= 4.0:
            signal = "UP"
        elif pct_chg <= -2.3:
            signal = "DOWN"
        else:
            signal = "NEUTRAL"
        points.append(
            ActiveMarketValuePoint(
                date=str(row["date"]).strip(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=close,
                volume=float(row["volume"]),
                amount=float(row["amount"]),
                pct_chg=round(pct_chg, 4),
                signal=signal,
            )
        )
        prev_close = close

    # 两日累计涨幅：今日 close / 前 2 个交易日 close - 1
    for i, point in enumerate(points):
        if i >= 2 and points[i - 2].close > 0:
            point.cum2_pct = round((point.close / points[i - 2].close - 1.0) * 100.0, 4)
    return points


@lru_cache(maxsize=2)
def _load_csv_cached(path: str) -> list[ActiveMarketValuePoint]:
    """从 CSV 加载（带缓存）。"""
    csv_path = Path(path)
    raw_rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_rows.append(
                {
                    "date": row["date"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                    "amount": row["amount"],
                }
            )
    return _finalize_points(raw_rows)


@lru_cache(maxsize=4)
def _load_duckdb_cached(duckdb_path: str) -> list[ActiveMarketValuePoint]:
    """从 DuckDB 的 active_market_value 表加载（带缓存）。"""
    try:
        import duckdb  # noqa: PLC0415
    except ImportError as e:
        raise RuntimeError("需要安装 duckdb 包才能读取 DuckDB") from e

    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        rows = con.execute(
            "SELECT CAST(date AS VARCHAR) AS date, open, high, low, close, volume, amount "
            "FROM active_market_value ORDER BY date"
        ).fetchall()
    finally:
        con.close()

    raw_rows = [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5], "amount": r[6]}
        for r in rows
    ]
    return _finalize_points(raw_rows)


def load_active_market_value(
    path: Optional[str] = None,
    duckdb_path: Optional[str] = None,
) -> list[ActiveMarketValuePoint]:
    """加载 0AMV 日线数据（带缓存）。

    优先 DuckDB（active_market_value 表），未提供 DuckDB 或表为空时使用 CSV。

    Args:
        path: CSV 路径；None 使用项目默认路径。
        duckdb_path: DuckDB 数据库路径；提供时优先从 DuckDB 读取。

    Returns:
        按日期升序的活跃市值点列表。
    """
    if duckdb_path:
        try:
            rows = _load_duckdb_cached(duckdb_path)
            if rows:
                return rows
        except Exception:  # noqa: BLE001
            # DuckDB 表不存在或读取失败时回退 CSV
            pass
    return _load_csv_cached(str(path or default_path()))


def _normalize_query_date(date: str) -> str:
    """把 YYYYMMDD 转成 CSV 里的 YYYY-MM-DD。"""
    s = str(date).replace("-", "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return str(date)


def get_active_market_value(
    date: Optional[str] = None,
    path: Optional[str] = None,
    duckdb_path: Optional[str] = None,
) -> ActiveMarketValuePoint | None:
    """获取指定日期或最新一日的活跃市值数据。"""
    rows = load_active_market_value(path, duckdb_path)
    if not rows:
        return None

    if date is None:
        return rows[-1]

    target = _normalize_query_date(date)
    for row in rows:
        if row.date == target:
            return row
    return None


def get_active_market_signal(
    date: Optional[str] = None,
    up_threshold: float = 4.0,
    down_threshold: float = -2.3,
    path: Optional[str] = None,
    duckdb_path: Optional[str] = None,
) -> str:
    """获取活跃市值择时信号：UP / DOWN / NEUTRAL；无数据返回 NEUTRAL。"""
    point = get_active_market_value(date, path, duckdb_path)
    if point is None:
        return "NEUTRAL"
    if point.pct_chg >= up_threshold:
        return "UP"
    if point.pct_chg <= down_threshold:
        return "DOWN"
    return "NEUTRAL"


def _cum_pct(rows: list[ActiveMarketValuePoint], idx: int, lookback: int) -> float | None:
    """计算第 idx 天相对前 lookback 个交易日收盘的累计涨幅（%）。"""
    if idx < lookback:
        return None
    base = rows[idx - lookback].close
    if base <= 0:
        return None
    return (rows[idx].close / base - 1.0) * 100.0


def get_active_market_gate(
    date: Optional[str] = None,
    open_lookback: int = 2,
    open_threshold: float = 4.0,
    clear_threshold: float = -2.3,
    path: Optional[str] = None,
    duckdb_path: Optional[str] = None,
) -> str:
    """活跃市值全局交易闸门。

    规则：
    - 累计涨幅（默认 2 日）> open_threshold（默认 +4%）→ OPEN，允许开仓
    - 当日跌幅 <= clear_threshold（默认 -2.3%） 或 累计跌幅 <= clear_threshold → CLEAR，清仓
    - 其他情况 → WAIT，不开新仓

    Returns:
        OPEN / WAIT / CLEAR
    """
    rows = load_active_market_value(path, duckdb_path)
    if not rows:
        return "WAIT"

    if date is None:
        idx = len(rows) - 1
    else:
        target = _normalize_query_date(date)
        idx = next((i for i, r in enumerate(rows) if r.date == target), -1)
        if idx < 0:
            return "WAIT"

    point = rows[idx]
    cum = _cum_pct(rows, idx, open_lookback)

    if point.pct_chg <= clear_threshold:
        return "CLEAR"
    if cum is not None and cum <= clear_threshold:
        return "CLEAR"
    if cum is not None and cum > open_threshold:
        return "OPEN"
    return "WAIT"


def format_active_market_value(point: ActiveMarketValuePoint) -> str:
    """人类可读输出。"""
    signal_text = {
        "UP": "多头（+4% 以上）",
        "DOWN": "空头（-2.3% 以下）",
        "NEUTRAL": "中性",
    }.get(point.signal, point.signal)
    return (
        f"活跃市值(0AMV) · {point.date}\n"
        f"收盘: {point.close:,.2f}\n"
        f"日环比: {point.pct_chg:+.2f}%\n"
        f"信号: {signal_text}"
    )


def import_0amv_csv_to_duckdb(csv_path: str, duckdb_path: str) -> int:
    """把 0AMV CSV 导入 DuckDB 的 active_market_value 表。

    Args:
        csv_path: 源 CSV 路径。
        duckdb_path: 目标 DuckDB 数据库路径。

    Returns:
        导入行数。
    """
    try:
        import duckdb  # noqa: PLC0415
    except ImportError as e:
        raise RuntimeError("需要安装 duckdb 包") from e

    points = load_active_market_value(path=csv_path)
    if not points:
        return 0

    con = duckdb.connect(duckdb_path)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS active_market_value (
                date DATE PRIMARY KEY,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                amount DOUBLE,
                source VARCHAR,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.executemany(
            """
            INSERT INTO active_market_value
                (date, open, high, low, close, volume, amount, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '0amv_csv', now())
            ON CONFLICT (date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                amount = excluded.amount,
                source = excluded.source,
                updated_at = now()
            """,
            [
                (
                    point.date,
                    point.open,
                    point.high,
                    point.low,
                    point.close,
                    point.volume,
                    point.amount,
                )
                for point in points
            ],
        )
    finally:
        con.close()
    return len(points)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="活跃市值 0AMV")
    parser.add_argument("--date", default=None, help="日期 YYYY-MM-DD，默认最新")
    parser.add_argument("--path", default=None, help="CSV 路径")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    point = get_active_market_value(args.date, args.path)
    if point is None:
        print("未找到数据")
        raise SystemExit(1)

    gate = get_active_market_gate(args.date, path=args.path)

    if args.json:
        data = point.__dict__.copy()
        data["gate"] = gate
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_active_market_value(point))
        print(f"全局闸门: {gate}")