import math

import numpy as np
import pandas as pd
import pytest

from app.analysis import config as C
from app.analysis import engine, regime, scoring
from app.analysis.indicators import (
    Indicator,
    build,
    change_over,
    latest,
    on_dates,
    rolling_scaled,
    rolling_z,
    transform,
)


def frame(values, index, pub_lag_days=0) -> pd.DataFrame:
    idx = pd.DatetimeIndex(index, name="ref_date")
    return pd.DataFrame({"value": np.asarray(values, dtype=float),
                         "published_at": idx + pd.Timedelta(days=pub_lag_days)}, index=idx)


def monthly(values, start="2010-01-01", lag=0):
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return frame(values, idx, lag)


# ---- indicators -------------------------------------------------------------------------
def test_change_over_pct_and_diff():
    s = monthly([100, 101, 102, 103, 110])["value"]
    assert change_over(s, 3, "pct").iloc[-1] == pytest.approx((110 / 101 - 1) * 100)
    assert change_over(s, 1, "diff").iloc[-1] == pytest.approx(7)
    assert math.isnan(change_over(s, 3, "pct").iloc[2])  # no value 3 months before


def test_change_over_uses_last_value_before_target_for_irregular_dates():
    idx = pd.to_datetime(["2026-01-02", "2026-01-30", "2026-04-29", "2026-04-30"])
    s = pd.Series([10.0, 12.0, 13.0, 15.0], index=idx)
    # 2026-04-30 minus 3 months = 2026-01-30 → 12
    assert change_over(s, 3, "diff").iloc[-1] == pytest.approx(3)
    # 2026-04-29 minus 3 months = 2026-01-29 → last on/before is 2026-01-02 → 10
    assert change_over(s, 3, "diff").iloc[-2] == pytest.approx(3)


def test_rolling_z_matches_manual_calculation():
    vals = np.arange(80, dtype=float) % 7
    s = monthly(vals)["value"]
    z = rolling_z(s, years=5, min_years=3)
    window = s[s.index > s.index[-1] - pd.Timedelta(days=int(5 * 365.25))].to_numpy()
    med = np.median(window)
    mad = np.median(np.abs(window - med))
    assert z.iloc[-1] == pytest.approx((s.iloc[-1] - med) / (1.4826 * mad))


def test_robust_z_is_not_flattened_by_one_extreme_episode():
    """The 2020 problem: a crash inside the window must not hide later normal moves."""
    rng = np.random.default_rng(3)
    vals = rng.normal(0, 1, 72)
    vals[30:33] = [-60, -40, 30]  # one-off shock, like payrolls in 2020
    vals[-1] = 2.5  # a clearly unusual reading later on
    s = monthly(vals)["value"]
    import app.analysis.indicators as I

    robust = rolling_z(s, 5, 3).iloc[-1]
    I.ROBUST = False
    try:
        classic = rolling_z(s, 5, 3).iloc[-1]
    finally:
        I.ROBUST = True
    assert robust > 1.8  # still reads as unusual
    assert classic < 0.5  # the classic z-score hides it


def test_robust_stats_on_daily_series_use_weekly_sample_without_lookahead():
    idx = pd.bdate_range("2015-01-01", "2020-12-31")
    s = pd.Series(np.sin(np.arange(len(idx)) / 20), index=idx)
    z = rolling_z(s, 5, 3)
    assert z.notna().sum() > 0
    # Changing the last value changes only the last z: stats come from earlier weeks
    s2 = s.copy()
    s2.iloc[-1] = 50
    z2 = rolling_z(s2, 5, 3)
    assert (z2.iloc[:-1].dropna() == z.iloc[:-1].dropna()).all()


def test_rolling_z_needs_min_history():
    s = monthly(np.random.default_rng(0).normal(size=60))["value"]
    z = rolling_z(s, years=5, min_years=3)
    assert z.loc[: s.index[0] + pd.Timedelta(days=1090)].isna().all()
    assert z.iloc[-1] == z.iloc[-1]  # not NaN


def test_rolling_z_constant_series_is_nan_not_infinite():
    s = monthly([5.0] * 60)["value"]
    assert rolling_z(s, 5, 3).isna().all()


def test_scaled_change_keeps_sign():
    # Always growing, at a slowing pace: z of the change goes negative, scaled stays positive
    vals = np.linspace(3.0, 1.0, 60)
    s = monthly(vals)["value"]
    assert (rolling_scaled(s, 5, 3).dropna() > 0).all()
    assert rolling_z(s, 5, 3).dropna().iloc[-1] < 0


def test_yoy_transform():
    f = monthly(np.linspace(100, 123, 24))
    ind = Indicator("x", "X", "macro", ("S",), "yoy", "diff", "% a/a")
    out = transform(ind, {"S": f})
    assert out["value"].iloc[-1] == pytest.approx((123 / f["value"].iloc[11] - 1) * 100)
    assert out["value"].iloc[:12].isna().sum() == 0  # NaN rows are dropped
    assert len(out) == 12


def test_spread_transform_and_availability():
    a = frame([4.0, 4.1], pd.to_datetime(["2026-11-18", "2026-11-19"]), 1)
    b = frame([3.88], pd.to_datetime(["2026-11-18"]), 3)
    ind = Indicator("x", "X", "market", ("A", "B"), "spread", "diff", "punti %")
    out = transform(ind, {"A": a, "B": b})
    assert list(out["value"].round(2)) == [0.12, 0.22]
    # Known only when both legs are published
    assert out["available"].iloc[0] == pd.Timestamp("2026-11-21")


def test_latest_respects_publication_date():
    f = monthly([1.0, 2.0, 3.0], lag=40)  # each month published 40 days later
    ind = Indicator("x", "X", "macro", ("S",), "level", "diff", "u")
    df = build(ind, {"S": f})
    row = latest(df, pd.Timestamp("2010-03-15"))  # March value published 10 April
    assert row["value"] == 2.0


def test_on_dates_uses_publication_not_reference_date():
    f = monthly([1.0, 2.0, 3.0], lag=40)
    ind = Indicator("x", "X", "macro", ("S",), "level", "diff", "u")
    df = build(ind, {"S": f})
    v = on_dates(df, "value", pd.DatetimeIndex(["2010-02-01", "2010-02-10", "2010-04-15"]))
    assert math.isnan(v.iloc[0]) and v.iloc[1] == 1.0 and v.iloc[2] == 3.0


# ---- scoring -----------------------------------------------------------------------------
def test_weighted_mean_clips_and_reports_coverage():
    mean, cov = scoring.weighted_mean([(10.0, 1), (0.0, 1), (None, 2)])
    assert mean == pytest.approx(1.5)  # 10 clipped to 3
    assert cov == pytest.approx(0.5)


@pytest.mark.parametrize("m,k,expected", [
    (1.0, 1.0, 100), (1.0, -1.0, -100), (2.0, 1.0, 50), (-2.0, -2.0, 100),
    (2.0, 0.0, 0), (0.1, -0.1, 0), (None, 1.0, None),
])
def test_convergence(m, k, expected):
    assert scoring.convergence(m, k) == expected


def test_scenario_score_scale():
    assert scoring.scenario_score(2.0, 2.0) == 100
    assert scoring.scenario_score(1.0, 0.0) == 25
    assert scoring.scenario_score(-5.0, -5.0) == -100


def test_divergence_threshold_and_alarm():
    past = [i / 100 for i in range(100)]  # gaps 0.00 .. 0.99
    thr, basis = scoring.divergence_threshold(past)
    assert basis == "storica" and thr == pytest.approx(0.89)
    assert scoring.divergence(0.0, 0.5, thr) is None
    alarm = scoring.divergence(-0.5, 0.5, thr)
    assert alarm == {"gap": 1.0, "leader": "mercato"}
    assert scoring.divergence(1.0, 0.0, thr)["leader"] == "macro"
    assert scoring.gap_percentile(0.5, past) == pytest.approx(0.5)


def test_divergence_threshold_falls_back_without_history():
    assert scoring.divergence_threshold([0.1] * 5) == (C.DIVERGENCE_FALLBACK, "fissa")


def test_stance():
    assert scoring.stance(0.3) == "sostiene"
    assert scoring.stance(-0.3) == "contraddice"
    assert scoring.stance(0.1) == "neutro"
    assert scoring.stance(None) == "mancante"


# ---- regime ------------------------------------------------------------------------------
@pytest.mark.parametrize("liq,g,i,name", [
    (1, 1, 1, "Liquidità in espansione · Reflazione"),
    (1, 1, -1, "Liquidità in espansione · Goldilocks"),
    (-1, -1, 1, "Liquidità in contrazione · Stagflazione"),
    (-1, -1, -1, "Liquidità in contrazione · Rallentamento disinflazionistico"),
])
def test_classify(liq, g, i, name):
    assert regime.classify(liq, g, i)["name"] == name


def test_axis_score_applies_signs():
    signals = C.REGIME_AXES["growth"]
    values = {("payrolls", "s_chg3"): 1.0, ("unrate", "s_chg3"): 1.0,
              ("claims", "s_chg3"): None, ("indpro", "s_chg3"): 1.0}
    score, cov = regime.axis_score(signals, values)
    # payrolls +0.3, unrate −0.3 (rising unemployment is bad), indpro +0.2 over weight 0.8
    assert score == pytest.approx(0.2 / 0.8)
    assert cov == pytest.approx(0.8)


def test_forward_returns():
    p = frame([100, 110, 99], pd.to_datetime(["2020-01-31", "2020-02-28", "2020-03-31"]))
    r = regime.forward_returns(p, pd.DatetimeIndex(["2020-01-31", "2020-02-29", "2020-03-31"]))
    assert r.iloc[0] == pytest.approx(10.0)
    assert r.iloc[1] == pytest.approx(-10.0)
    assert math.isnan(r.iloc[2])


# ---- engine end to end on synthetic data ------------------------------------------------
def synthetic_frames(seed=1, start="2005-01-01", end="2026-11-20"):
    rng = np.random.default_rng(seed)
    frames = {}
    for sid in engine.required_series():
        daily = sid in {"DFF", "DGS10", "DGS2", "T10Y2Y", "T10YIE", "BAMLH0A0HYM2", "BAMLC0A0CM",
                        "BAA10Y", "DTWEXBGS", "COPPER_GOLD", "CYCL_DEF", "VIX", "OIL_WTI",
                        "GOLD", "SPY"} or sid.startswith("XL")
        weekly = sid in {"FED_NET_LIQ", "ECBASSETSW", "ICSA", "CCSA"}
        freq = "B" if daily else "W-WED" if weekly else "MS"
        idx = pd.date_range(start, end, freq=freq)
        walk = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, len(idx))))
        lag = 0 if daily else 7 if weekly else 30
        frames[sid] = frame(walk, idx, lag)
    return frames


def test_analyze_end_to_end_shape():
    r = engine.analyze(synthetic_frames(), pd.Timestamp("2026-11-21"))
    assert r["regime"]["available"]
    assert set(r["regime"]["axes"]) == {"liquidity", "growth", "inflation"}
    assert len(r["scenarios"]) == len(C.SCENARIOS)
    for sc in r["scenarios"]:
        assert -100 <= sc["score"] <= 100
        assert sc["convergence"] is None or -100 <= sc["convergence"] <= 100
        assert sc["divergence_threshold"]["basis"] == "storica"
        n = len(sc["supports"]) + len(sc["contradicts"]) + len(sc["neutral"])
        assert n == len(next(s for s in C.SCENARIOS if s.id == sc["id"]).signals)
    assert r["regime"]["history"]["months"] > 100
    assert all(i["available"] for i in r["indicators"])
    assert r["verdict"]["text"]


def test_analyze_is_point_in_time():
    """Data published after as_of must not change the analysis."""
    frames = synthetic_frames()
    as_of = pd.Timestamp("2020-06-30")
    base = engine.analyze(frames, as_of, with_history=False)

    poisoned = {}
    for sid, f in frames.items():
        f = f.copy()
        late = f["published_at"] > as_of
        f.loc[late, "value"] = f.loc[late, "value"] * 50  # absurd future values
        poisoned[sid] = f
    again = engine.analyze(poisoned, as_of, with_history=False)
    assert again["scenarios"] == base["scenarios"]
    assert again["regime"]["axes"] == base["regime"]["axes"]


def test_verdict_mixed_when_scores_are_close():
    sc = [{"id": "a", "name": "A", "score": 30}, {"id": "b", "name": "B", "score": 25}]
    v = engine._verdict(sc)
    assert v["mixed"] and v["scenario"] is None and "A e B" in v["text"]
    sc[1]["score"] = 5
    assert engine._verdict(sc)["scenario"] == "a"


def test_config_references_are_valid():
    for axis in C.REGIME_AXES.values():
        for s in axis:
            assert s.indicator in C.INDICATOR_BY_ID and s.field in C.FIELD_LABELS
    for sc in C.SCENARIOS:
        voices = {C.INDICATOR_BY_ID[s.indicator].voice for s in sc.signals}
        assert voices == {"macro", "market"}, f"{sc.id} needs both voices"
        for s in sc.signals:
            assert s.field in C.FIELD_LABELS


def test_robust_scale_does_not_collapse_on_a_series_that_barely_moved():
    """Unemployment 2003-2005: mostly unchanged months; a +0.7 move must not be ±7σ."""
    rng = np.random.default_rng(5)
    steps = rng.choice([0.0, 0.0, 0.0, 0.0, 0.1, -0.1, 0.2, -0.2], size=72)
    steps[-1] = 0.7
    s = monthly(steps)["value"]
    assert 1.5 < rolling_z(s, 5, 3).iloc[-1] < 6
