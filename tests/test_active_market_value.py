"""活跃市值 0AMV 模块单元测试。"""

from pathlib import Path

from modules.active_market_value import (
    get_active_market_gate,
    get_active_market_signal,
    get_active_market_value,
    load_active_market_value,
)


def _write_csv(tmp_path: Path, lines: str) -> str:
    path = tmp_path / "0amv.csv"
    path.write_text(lines, encoding="utf-8")
    return str(path)


def test_load_and_signal(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"  # BOM 兼容
        "2026-08-01,100,102,99,101,1000,101000\n"
        "2026-08-02,101,104,100,106,1200,127200\n"  # +4.95% -> UP
        "2026-08-03,106,107,100,102,1100,112200\n"  # -3.77% -> DOWN
        "2026-08-04,102,103,101,102.5,1000,102500\n",  # +0.49% -> NEUTRAL
    )
    rows = load_active_market_value(csv_path)
    assert len(rows) == 4
    assert rows[1].signal == "UP"
    assert rows[2].signal == "DOWN"
    assert rows[3].signal == "NEUTRAL"


def test_get_active_market_value_by_date(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"
        "2026-08-01,100,102,99,101,1000,101000\n"
        "2026-08-02,101,104,100,106,1200,127200\n",
    )
    point = get_active_market_value("20260802", csv_path)
    assert point is not None
    assert point.date == "2026-08-02"
    assert get_active_market_signal("20260802", path=csv_path) == "UP"


def test_get_active_market_value_latest(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"
        "2026-08-01,100,102,99,101,1000,101000\n",
    )
    point = get_active_market_value(None, csv_path)
    assert point is not None
    assert point.date == "2026-08-01"


def test_active_market_gate(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"
        "2026-08-01,100,102,99,100,1000,100000\n"
        "2026-08-02,100,102,98,98,1000,98000\n"
        "2026-08-03,98,106,97,105,1200,126000\n"  # 2日累计 +5.00% -> OPEN
        "2026-08-04,105,106,100,101.2,1100,111320\n",  # 当日 -3.62% -> CLEAR
    )
    assert get_active_market_gate("20260803", path=csv_path) == "OPEN"
    assert get_active_market_gate("20260804", path=csv_path) == "CLEAR"