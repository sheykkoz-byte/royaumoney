import math

import pandas as pd
import pytest

from app import derived


def frame(values: dict[str, float], pub_lag_days: int = 0) -> pd.DataFrame:
    idx = pd.DatetimeIndex(pd.to_datetime(list(values)), name="ref_date")
    return pd.DataFrame(
        {"value": list(values.values()), "published_at": idx + pd.Timedelta(days=pub_lag_days)},
        index=idx,
    )


def test_fed_net_liquidity_uses_last_rrp_on_or_before_wednesday():
    walcl = frame({"2026-11-11": 6750.0, "2026-11-18": 6741.452}, 1)
    tga = frame({"2026-11-11": 900.0, "2026-11-18": 916.613}, 1)
    # No RRP on the 18th itself (e.g. holiday): use the 17th
    rrp = frame({"2026-11-10": 2.0, "2026-11-11": 1.0, "2026-11-17": 0.401, "2026-11-19": 9.9})
    out = derived.fed_net_liquidity(walcl, tga, rrp)
    assert out.loc["2026-11-11", "value"] == pytest.approx(6750 - 900 - 1)
    assert out.loc["2026-11-18", "value"] == pytest.approx(6741.452 - 916.613 - 0.401)
    assert out.loc["2026-11-18", "published_at"] == pd.Timestamp("2026-11-19")


def test_fed_net_liquidity_drops_dates_without_rrp_history():
    walcl = frame({"2002-12-18": 700.0, "2003-03-05": 710.0})
    tga = frame({"2002-12-18": 5.0, "2003-03-05": 6.0})
    rrp = frame({"2003-02-07": 0.0})
    out = derived.fed_net_liquidity(walcl, tga, rrp)
    assert list(out.index) == [pd.Timestamp("2003-03-05")]


def test_fx_conversion_multiply_and_divide():
    ecb = frame({"2026-11-13": 5906.258})
    usd_per_eur = frame({"2026-11-12": 1.10, "2026-11-13": 1.1034})
    out = derived.convert_with_fx(ecb, usd_per_eur, multiply=True)
    assert out["value"].iloc[0] == pytest.approx(5906.258 * 1.1034)


def test_fx_conversion_period_end_uses_month_end_rate():
    boj = frame({"2026-10-01": 626188.2}, 33)  # billions of yen, end-of-October value
    jpy = frame({"2026-10-01": 150.0, "2026-10-30": 160.0, "2026-11-03": 999.0})
    out = derived.convert_with_fx(boj, jpy, multiply=False, period_end=True)
    assert out["value"].iloc[0] == pytest.approx(626188.2 / 160.0)
    # published_at is the later of the two inputs
    assert out["published_at"].iloc[0] == pd.Timestamp("2026-11-03")


def test_ratio_only_on_common_dates():
    cu = frame({"2026-11-19": 5.625, "2026-11-20": 5.465})
    au = frame({"2026-11-20": 3539.0, "2026-11-21": 3540.0})
    out = derived.ratio(cu, au, factor=1000)
    assert len(out) == 1
    assert out["value"].iloc[0] == pytest.approx(5.465 / 3539.0 * 1000)


def test_cyclicals_vs_defensives_is_scale_free_and_starts_at_100():
    dates = ["2026-01-02", "2026-01-05"]
    cyc = {"A": frame(dict(zip(dates, [10.0, 11.0]))), "B": frame(dict(zip(dates, [200.0, 200.0])))}
    dfn = {"C": frame(dict(zip(dates, [50.0, 50.0])))}
    out = derived.cyclicals_vs_defensives(cyc, dfn)
    assert out["value"].iloc[0] == pytest.approx(100.0)
    # A +10%, B flat → geometric mean +sqrt(1.1); defensives flat
    assert out["value"].iloc[1] == pytest.approx(100 * math.sqrt(1.1))
    # Multiplying one ETF's price level changes nothing
    cyc["B"] = frame(dict(zip(dates, [2000.0, 2000.0])))
    assert derived.cyclicals_vs_defensives(cyc, dfn)["value"].iloc[1] == pytest.approx(
        100 * math.sqrt(1.1))


def test_empty_input_gives_empty_output():
    assert derived.ratio(derived.EMPTY, frame({"2026-11-20": 1.0})).empty
