"""市场择时指标模块单元测试。"""

from modules.indicators import DailyData
from modules.market_timing import (
    _breadth_score,
    _classify_regime,
    _moneyflow_score,
    _normalize_date,
    _risk_score,
    _sentiment_score,
)


def test_normalize_date():
    assert _normalize_date("20260821") == "2026-08-21"
    assert _normalize_date("2026-08-21") == "2026-08-21"


def test_breadth_score():
    snapshot = {
        "total": 100,
        "advancers": 60,
        "decliners": 40,
        "limit_up": 5,
        "limit_down": 1,
        "strong_up": 10,
        "strong_down": 5,
    }
    score = _breadth_score(snapshot)
    assert 0 <= score <= 100
    assert score > 50


def test_moneyflow_score():
    amount_history = [100.0] * 20
    snapshot = {"total_amount": 120.0}
    score, ratio = _moneyflow_score(amount_history, snapshot)
    assert ratio == 1.2
    assert score == 60.0


def test_risk_score_rising_market():
    klines = []
    price = 100.0
    for i in range(30):
        price *= 1.005
        klines.append(
            DailyData(
                ts_code="000001.SH",
                trade_date=f"202601{i+1:02d}",
                open=price * 0.99,
                high=price * 1.01,
                low=price * 0.98,
                close=price,
                vol=10000.0,
                amount=price * 10000.0,
                pct_chg=0.5,
                prev_close=price / 1.005,
            )
        )
    score, vol, dd = _risk_score(klines)
    assert 0 <= score <= 100
    assert dd > -0.05


def test_sentiment_score():
    snapshot = {
        "total": 100,
        "advancers": 60,
        "decliners": 40,
        "limit_up": 5,
        "limit_down": 1,
    }
    score = _sentiment_score(snapshot)
    assert 0 <= score <= 100
    assert score > 50


def test_classify_regime():
    assert _classify_regime(70) == "强势"
    assert _classify_regime(50) == "震荡"
    assert _classify_regime(30) == "弱势"