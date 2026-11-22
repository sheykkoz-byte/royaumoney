import math

import numpy as np
import pandas as pd
import pytest

from app.rqe import allocation, assets, backtest, macro
from app.rqe import config as C


# ---- macro --------------------------------------------------------------------------------
def test_probabilities_are_symmetric_and_sum_to_one():
    assert macro.p_rising(0.0) == pytest.approx(0.5)
    assert macro.p_rising(1.0) == pytest.approx(1 - macro.p_rising(-1.0))
    probs = macro.quadrant_probs(0.8, 0.3)
    assert sum(probs.values()) == pytest.approx(1.0)
    assert max(probs, key=probs.get) == "A"  # growth up, inflation down
    assert probs["A"] == pytest.approx(0.8 * 0.7)


def test_regime_changes_use_hysteresis():
    idx = pd.date_range("2020-01-31", periods=5, freq="ME")
    h = pd.DataFrame({"dominante": ["A", "B", "B", "C", "C"],
                      "A": [.6, .3, .2, .1, .1], "B": [.2, .35, .5, .2, .1],
                      "C": [.1, .2, .2, .45, .6], "D": [.1, .15, .1, .25, .2]}, index=idx)
    ev = macro.regime_changes(h, min_prob=0.4)
    # Feb: B only 35% → no alert; Mar: B 50% → A→B; Apr: C 45% → B→C
    assert [(e["da"], e["a"]) for e in ev] == [("A", "B"), ("B", "C")]
    assert ev[0]["data"] == "2020-03-31"


def _versions(values: dict[str, float], pub_lag_days=15, revision=None):
    """Monthly series as a versions table; optional later revision {ref: (value, pub)}."""
    rows = [{"ref_date": pd.Timestamp(d), "published_at": pd.Timestamp(d) + pd.Timedelta(days=pub_lag_days),
             "value": v} for d, v in values.items()]
    for d, (v, pub) in (revision or {}).items():
        rows.append({"ref_date": pd.Timestamp(d), "published_at": pd.Timestamp(pub), "value": v})
    return pd.DataFrame(rows).sort_values(["ref_date", "published_at"]).reset_index(drop=True)


def test_history_is_point_in_time_including_revisions(monkeypatch):
    """A revision published after a date must not change the regime seen at that date."""
    monkeypatch.setattr(C, "GROWTH", [C.Component("G", "g", "level", 1, 1.0)])
    monkeypatch.setattr(C, "INFLATION", [C.Component("I", "i", "level", 1, 1.0)])
    rng = np.random.default_rng(0)
    dates = pd.date_range("2010-01-01", "2018-12-01", freq="MS")
    g = dict(zip(dates, np.cumsum(rng.normal(0, 1, len(dates)))))
    i = dict(zip(dates, np.cumsum(rng.normal(0, 1, len(dates)))))
    eval_dates = pd.DatetimeIndex(["2016-06-30", "2017-06-30"])
    base = macro.history({"G": _versions(g), "I": _versions(i)}, eval_dates)
    # Revise 2016-05 growth massively, but publish the revision only in 2017
    rev = macro.history({"G": _versions(g, revision={"2016-05-01": (g[pd.Timestamp("2016-05-01")] + 50, "2017-03-01")}),
                         "I": _versions(i)}, eval_dates)
    assert rev.loc["2016-06-30", "crescita"] == pytest.approx(base.loc["2016-06-30", "crescita"])
    assert rev.loc["2017-06-30", "crescita"] != pytest.approx(base.loc["2017-06-30", "crescita"])


# ---- allocation ---------------------------------------------------------------------------
def monthly_returns(vols: dict[str, float], n=24, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-31", periods=n, freq="ME")
    df = pd.DataFrame({a: rng.normal(0.005, v, n) for a, v in vols.items()}, index=idx)
    df["cash"] = 0.001
    return df


def test_risk_parity_weights_are_inverse_volatility():
    r = monthly_returns({"equity": 0.04, "long_tsy": 0.02, "gold": 0.04, "tips": np.nan})
    w = allocation.risk_parity(r)
    assert set(w) == {"equity", "long_tsy", "gold"}  # TIPS without history is left out
    assert sum(w.values()) == pytest.approx(1)
    vol = r[["equity", "long_tsy", "gold"]].tail(12).std()
    assert w["long_tsy"] / w["equity"] == pytest.approx(vol["equity"] / vol["long_tsy"])


@pytest.mark.parametrize("probs", [{"A": 1, "B": 0, "C": 0, "D": 0},
                                   {"A": 0, "B": 0, "C": 1, "D": 0},
                                   {"A": .25, "B": .25, "C": .25, "D": .25}])
def test_tilt_respects_limits(probs):
    base = {"equity": .2, "long_tsy": .2, "int_tsy": .2, "tips": .15, "gold": .1,
            "commodities": .15}
    w = allocation.tilt(base, probs, max_dev=0.10)
    assert sum(w.values()) == pytest.approx(1)
    for a in base:
        assert abs(w[a] - base[a]) <= 0.10 + 1e-9
    assert 0 <= w["cash"] <= 0.10 + 1e-9


def test_tilt_direction_follows_the_regime():
    base = {"equity": .2, "long_tsy": .2, "int_tsy": .2, "tips": .15, "gold": .1,
            "commodities": .15}
    goldilocks = allocation.tilt(base, {"A": 1, "B": 0, "C": 0, "D": 0})
    stagflation = allocation.tilt(base, {"A": 0, "B": 0, "C": 1, "D": 0})
    assert goldilocks["equity"] > base["equity"] > stagflation["equity"]
    assert stagflation["gold"] > base["gold"] and stagflation["cash"] > 0
    assert goldilocks["cash"] == 0


# ---- assets & backtest --------------------------------------------------------------------
def test_bond_proxy_carry_minus_duration():
    idx = pd.date_range("2020-01-01", "2020-02-29", freq="D")
    y = pd.Series(np.where(idx < pd.Timestamp("2020-02-01"), 4.0, 4.5), index=idx)
    r = assets.bond_proxy(y, duration=10)
    assert r.iloc[-1] == pytest.approx(0.04 / 12 - 10 * 0.005)


def test_splice_prefers_the_etf():
    idx = pd.date_range("2020-01-31", periods=3, freq="ME")
    etf = pd.Series([np.nan, 0.02, 0.03], index=idx)
    proxy = pd.Series([0.01, 0.5, 0.5], index=idx)
    assert list(assets.splice(etf, proxy)) == [0.01, 0.02, 0.03]


def test_stats_and_drawdown():
    r = pd.Series([0.1, -0.5, 0.2], index=pd.date_range("2020-01-31", periods=3, freq="ME"))
    assert backtest.max_drawdown(r) == pytest.approx(-0.5)
    st = backtest.stats(pd.Series([0.01] * 12, index=pd.date_range("2020-01-31", periods=12, freq="ME")),
                        pd.Series(0.0, index=pd.date_range("2020-01-31", periods=12, freq="ME")))
    assert st["cagr"] == pytest.approx(1.01 ** 12 - 1, abs=1e-4)


def test_backtest_uses_only_past_information():
    r = monthly_returns({a: 0.03 for a in C.RISKY}, n=30)
    probs = pd.DataFrame({q: 0.25 for q in C.QUADRANTS}, index=r.index)
    probs["dominante"] = "A"
    out = backtest.run(r, probs, cost_bps=0)
    first = out["returns"].index[0]
    assert first > r.index[C.VOL_MIN_MONTHS - 1]  # needs 6 months of history first
    # The bench earns exactly 60/40 of the next month's returns
    t = out["returns"].index[3]
    assert out["returns"].loc[t, "bench"] == pytest.approx(0.6 * r.loc[t, "equity"] + 0.4 * r.loc[t, "int_tsy"])
    assert set(out["stats"]) == set(backtest.STRATEGIES)
    assert math.isfinite(out["stats"]["rp"]["volatilita"])


# ---- calibration --------------------------------------------------------------------------
def test_smoothing_is_trailing_only():
    from app.rqe import calibrate

    idx = pd.date_range("2020-01-31", periods=4, freq="ME")
    hist = pd.DataFrame({"crescita": [1.0, 1.0, 1.0, -9.0], "inflazione": [0.0] * 4}, index=idx)
    p = calibrate.probs_from_scores(hist, sigma=0.6, smooth=3)
    # A shock in the last month cannot change earlier months
    assert p.iloc[2]["A"] == pytest.approx(calibrate.probs_from_scores(hist.iloc[:3], 0.6, 3).iloc[2]["A"])
    assert p[list("ABCD")].sum(axis=1).round(9).eq(1).all()


def test_learned_preferences_ignore_the_future():
    from app.rqe import calibrate

    r = monthly_returns({a: 0.03 for a in C.RISKY}, n=90, seed=3)
    probs = pd.DataFrame({"A": .7, "B": .1, "C": .1, "D": .1}, index=r.index)
    t = r.index[75]
    before = calibrate.learned_preferences(r, probs, t)
    r2 = r.copy()
    r2.loc[r.index[76]:, "equity"] = 0.5  # absurd future returns
    after = calibrate.learned_preferences(r2, probs, t)
    assert before == after
    assert all(-1 <= v <= 1 for q in before for v in before[q].values())


def test_learned_tilt_needs_five_years_of_history():
    from app.rqe import calibrate

    r = monthly_returns({a: 0.03 for a in C.RISKY}, n=40, seed=4)
    probs = pd.DataFrame({q: .25 for q in "ABCD"}, index=r.index)
    assert calibrate.learned_preferences(r, probs, r.index[-1]) is None


def test_significance_t_statistic():
    from app.rqe import calibrate

    idx = pd.date_range("2013-01-31", periods=120, freq="ME")
    rng = np.random.default_rng(0)
    base = pd.Series(rng.normal(0.005, 0.02, 120), index=idx)
    same = calibrate.significance(base, base)
    assert same["t"] == 0.0
    better = calibrate.significance(base + 0.002 + rng.normal(0, 0.001, 120), base)
    assert better["t"] > 2 and better["errore_sharpe"] == pytest.approx(round(1 / math.sqrt(10), 2))


def test_tilt_with_custom_preferences():
    base = {"equity": .5, "long_tsy": .5}
    prefs = {q: {"equity": 1.0, "long_tsy": -1.0, "cash": 0.0} for q in "ABCD"}
    w = allocation.tilt(base, {"A": 1, "B": 0, "C": 0, "D": 0}, tilts=prefs, max_dev=0.1)
    assert w["equity"] == pytest.approx(0.6) and w["long_tsy"] == pytest.approx(0.4)
