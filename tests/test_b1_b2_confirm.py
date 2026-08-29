"""B1观察+B2确认策略的单元测试。"""

import pytest

from modules.indicators import DailyData
from modules.strategies.b1_b2_confirm import B1B2Config, has_b1_in_window, is_b2_signal, is_high_open_skip
from modules.backtest.b1_b2_backtest import _run_stock_klines, _default_loop_config


def _make_klines(n=40, start="20260101"):
    """构造简单的 DailyData 序列，允许手工设置 KDJ 属性以绕过价格计算。"""
    out = []
    base = 10.0
    for i in range(n):
        date = f"{int(start) + i:08d}"
        out.append(
            DailyData(
                ts_code="TEST.SZ",
                trade_date=date,
                open=base * 0.99,
                high=base * 1.01,
                low=base * 0.98,
                close=base,
                vol=10000.0,
                amount=base * 10000.0,
                pct_chg=0.0,
                prev_close=base,
            )
        )
    return out


def _make_b2_klines():
    klines = _make_klines(40)
    # B1 出现在 index=26（B2 前 4 个交易日）
    klines[26].kdj_j = -15.0
    # B2 当天：涨幅 +5%，量是前日 3 倍，J=40
    klines[30].pct_chg = 5.0
    klines[30].vol = 30000.0
    klines[30].kdj_j = 40.0
    return klines


def test_config_validate():
    B1B2Config().validate()
    with pytest.raises(ValueError):
        B1B2Config(observe_min=5, observe_max=3).validate()
    with pytest.raises(ValueError):
        B1B2Config(b2_min_pct=0).validate()
    with pytest.raises(ValueError):
        B1B2Config(b2_min_vol_ratio=0.5).validate()


def test_has_b1_in_window():
    klines = _make_b2_klines()
    cfg = B1B2Config(observe_min=3, observe_max=5)
    # index=30 往前 4 天有 B1
    assert has_b1_in_window(klines, 30, cfg) is True
    # index=21 往前找不到（不足窗口）
    assert has_b1_in_window(klines, 21, cfg) is False


def test_is_b2_signal_ok():
    klines = _make_b2_klines()
    cfg = B1B2Config(observe_min=3, observe_max=5)
    assert is_b2_signal(klines, 30, cfg) is True


def test_is_b2_signal_reject_low_pct():
    klines = _make_b2_klines()
    klines[30].pct_chg = 2.0
    cfg = B1B2Config(observe_min=3, observe_max=5)
    assert is_b2_signal(klines, 30, cfg) is False


def test_is_b2_signal_reject_low_volume():
    klines = _make_b2_klines()
    klines[30].vol = 12000.0  # 1.2 倍，不足 2 倍
    cfg = B1B2Config(observe_min=3, observe_max=5)
    assert is_b2_signal(klines, 30, cfg) is False


def test_is_high_open_skip():
    klines = _make_klines(40)
    # entry_idx=31 开盘较前收高开 8%
    klines[30].close = 100.0
    klines[31].open = 108.0
    cfg = B1B2Config(max_gap_open_pct=5.0)
    assert is_high_open_skip(klines, 30, 31, cfg) is True
    cfg2 = B1B2Config(max_gap_open_pct=None)
    assert is_high_open_skip(klines, 30, 31, cfg2) is False


def test_run_stock_klines_smoke():
    klines = _make_b2_klines()
    # 给足 B2 后一天的成交量/价格，至少能正常跑完不抛异常
    trades = _run_stock_klines(klines, B1B2Config(), _default_loop_config())
    assert isinstance(trades, list)
