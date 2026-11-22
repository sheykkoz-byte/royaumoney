import pandas as pd
import pytest

from app import cabina
from app.cabina import METRICS, RULES, apply_transform, sparkline, tile


def monthly(values, end="2026-10-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


def daily(values, end="2026-11-20"):
    idx = pd.bdate_range(end=end, periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def test_every_metric_rule_exists_and_series_is_in_catalog():
    from app import catalog

    for m in METRICS:
        assert m.section in cabina.SECTIONS
        assert m.rule is None or m.rule in RULES
        catalog.get(m.id)  # raises if unknown


@pytest.mark.parametrize("last,state", [(-0.3, "rosso"), (0.1, "giallo"), (0.8, "verde")])
def test_curve_levels(last, state):
    s = daily([0.5] * 300 + [last])
    assert RULES["curve"](s, last)[0] == state


def test_curve_back_above_zero_after_inversion_is_a_warning():
    s = daily([-0.4] * 100 + [0.6] * 100)
    state, reading = RULES["curve"](s, 0.6)
    assert state == "giallo" and "inversione" in reading


def test_sahm_rule():
    calm = monthly([4.0] * 24)
    assert RULES["sahm"](calm, 4.0)[0] == "verde"
    rising = monthly([4.0] * 18 + [4.3, 4.5, 4.7, 4.8, 4.9, 5.0])
    assert RULES["sahm"](rising, 5.0)[0] == "rosso"


def test_yield_rule_reads_basis_points():
    s = daily([4.0] * 40 + [4.5])
    state, reading = RULES["yield"](s, 4.5)
    assert state == "rosso" and "+50 punti base" in reading


def test_yoy_transform():
    s = monthly([100.0] * 12 + [103.0])
    assert apply_transform(s, "yoy").iloc[-1] == pytest.approx(3.0)


def test_sparkline_is_capped_and_keeps_the_last_point():
    s = daily(list(range(400)))
    sp = sparkline(s, 50)
    assert len(sp) <= 51 and sp[-1][1] == 399


def test_tile_from_series():
    m = next(x for x in METRICS if x.id == "VIX")
    t = tile(m, daily([15.0] * 30 + [30.0]))
    assert t["value"] == 30.0 and t["state"] == "rosso"
    assert t["changes"]["1g"] == pytest.approx(100.0)
    assert t["tv"] == "CAPITALCOM:VIX"


def test_no_symbol_refused_by_tradingview_widgets():
    # TradingView refuses its TVC indices and CME/ICE futures in embedded charts
    refused = ("TVC:DXY", "TVC:VIX", "TVC:US", "COMEX:", "NYMEX:", "CBOT:", "ICEUS:")
    for m in METRICS:
        assert not (m.tv and any(r in m.tv for r in refused)), m.tv


def test_tile_without_data_says_so():
    m = METRICS[0]
    assert tile(m, pd.Series(dtype=float))["errore"] == "nessun dato"
