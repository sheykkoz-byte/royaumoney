import json
from datetime import date, datetime

import pandas as pd
import pytest

from app.predictions.evaluate import _weekly_closes, evaluate
from app.predictions.spec import PredictionSpec
from app.predictions.stats import brier, horizon_bucket, summarize
from app.sources.futures import Contract, contracts_from, estimate_spot

GOLD = json.loads(open("seeds/previsioni/2026-11-21-oro.json", encoding="utf-8").read())
CREATED = date(2026, 11, 21)  # Saturday


def spec(**over) -> PredictionSpec:
    return PredictionSpec.model_validate(GOLD | over)


def bars(rows: dict[str, tuple[float, float, float]]) -> pd.DataFrame:
    """rows: 'YYYY-MM-DD' → (high, low, close); open = close."""
    idx = [date.fromisoformat(d) for d in rows]
    h, lo, c = zip(*rows.values())
    return pd.DataFrame({"open": c, "high": h, "low": lo, "close": c}, index=idx)


def flat(start: str, end: str, close=3550.0, spread=20.0) -> dict:
    return {d.date().isoformat(): (close + spread, close - spread, close)
            for d in pd.bdate_range(start, end)}


# ---- the gold prediction -----------------------------------------------------------------
def test_full_path_hits_all_three_phases():
    rows = flat("2026-11-23", "2027-01-29")
    rows["2026-12-01"] = (3725.0, 3650.0, 3700.0)  # phase 1
    rows["2026-12-11"] = (3500.0, 3415.0, 3450.0)  # phase 2 (after the Fed)
    rows["2027-01-20"] = (3910.0, 3800.0, 3880.0)  # phase 3
    r = evaluate(spec(), CREATED, bars(rows), date(2027, 2, 1))
    assert r.status == "colpita" and r.resolved_on == date(2027, 1, 20)
    assert [t["status"] for t in r.targets] == ["raggiunta"] * 3
    assert [e.kind for e in r.events] == ["target_hit"] * 3 + ["hit"]


def test_phase_two_before_the_fed_does_not_count():
    rows = flat("2026-11-23", "2026-12-31")
    rows["2026-11-25"] = (3725.0, 3650.0, 3700.0)  # phase 1
    rows["2026-12-03"] = (3600.0, 3410.0, 3500.0)  # dip before 9/12: too early
    r = evaluate(spec(), CREATED, bars(rows), date(2026, 12, 31))
    assert r.status == "aperta"
    assert r.targets[1]["status"] == "attiva"


def test_phase_one_missed_means_expired():
    r = evaluate(spec(), CREATED, bars(flat("2026-11-23", "2026-12-15")), date(2026, 12, 15))
    assert r.status == "scaduta" and r.resolved_on == date(2026, 12, 9)
    assert r.targets[0]["status"] == "mancata"


def test_still_open_before_deadline():
    r = evaluate(spec(), CREATED, bars(flat("2026-11-23", "2026-11-27")), date(2026, 11, 28))
    assert r.status == "aperta" and r.last_bar == date(2026, 11, 27)
    assert r.extremes["high"] == 3570.0


def test_weekly_close_above_3800_before_fed_invalidates():
    rows = flat("2026-11-23", "2026-12-04")
    rows["2026-12-03"] = (3850.0, 3700.0, 3820.0)  # phase 1 touched here
    rows["2026-12-04"] = (3830.0, 3790.0, 3810.0)  # Friday close above 3,800
    r = evaluate(spec(), CREATED, bars(rows), date(2026, 12, 5))
    assert r.status == "invalidata" and r.resolved_on == date(2026, 12, 4)
    assert r.targets[0]["status"] == "raggiunta"
    assert r.rules[0]["triggered_on"] == "2026-12-04"


def test_daily_close_above_3800_midweek_is_not_a_weekly_close():
    rows = flat("2026-11-23", "2026-12-04")
    rows["2026-12-02"] = (3850.0, 3700.0, 3820.0)  # Wednesday close above 3,800
    r = evaluate(spec(), CREATED, bars(rows), date(2026, 12, 5))
    assert r.status == "aperta"


def test_weekly_close_not_final_until_week_is_over():
    rows = flat("2026-11-23", "2026-12-04")
    rows["2026-12-04"] = (3850.0, 3700.0, 3820.0)
    assert evaluate(spec(), CREATED, bars(rows), date(2026, 12, 4)).status == "aperta"
    assert evaluate(spec(), CREATED, bars(rows), date(2026, 12, 5)).status == "invalidata"


def test_weekly_close_above_3800_after_fed_is_allowed():
    rows = flat("2026-11-23", "2026-12-18")
    rows["2026-11-25"] = (3725.0, 3650.0, 3700.0)
    rows["2026-12-18"] = (3850.0, 3700.0, 3820.0)
    assert evaluate(spec(), CREATED, bars(rows), date(2026, 12, 19)).status == "aperta"


def test_weekly_close_below_3300_invalidates_any_time():
    rows = flat("2026-11-23", "2026-11-27")
    rows["2026-11-27"] = (3400.0, 3250.0, 3290.0)
    r = evaluate(spec(), CREATED, bars(rows), date(2026, 11, 28))
    assert r.status == "invalidata"


def test_offset_shifts_prices():
    rows = flat("2026-11-23", "2026-11-27", close=3600.0)
    rows["2026-11-25"] = (3705.0, 3600.0, 3650.0)  # 3705 + 18.44 ≥ 3720
    assert evaluate(spec(), CREATED, bars(rows), date(2026, 11, 28)).status == "aperta"
    r = evaluate(spec(), CREATED, bars(rows), date(2026, 11, 28), offset=18.44)
    assert r.targets[0]["status"] == "raggiunta"
    assert r.targets[0]["hit_price"] == pytest.approx(3723.44)


def test_bars_on_or_before_creation_are_ignored():
    rows = flat("2026-11-16", "2026-11-27")
    rows["2026-11-20"] = (3800.0, 3500.0, 3520.0)  # before creation
    r = evaluate(spec(), CREATED, bars(rows), date(2026, 11, 28))
    assert r.targets[0]["status"] == "attiva"


def test_same_day_target_and_touch_invalidation_is_invalidated():
    s = spec(invalidations=[{"kind": "touch_below", "level": 3300, "description": "sotto 3.300"}])
    rows = flat("2026-11-23", "2026-11-27")
    rows["2026-11-25"] = (3730.0, 3290.0, 3500.0)
    r = evaluate(s, CREATED, bars(rows), date(2026, 11, 28))
    assert r.status == "invalidata"
    assert r.events[-1].data["ambiguous"] is True


def test_next_target_starts_the_day_after():
    s = spec(targets=[
        {"label": "su", "kind": "touch_above", "zone_low": 3700, "zone_high": 3700,
         "deadline": "2026-12-31"},
        {"label": "giù", "kind": "touch_below", "zone_low": 3400, "zone_high": 3400,
         "deadline": "2026-12-31"}], invalidations=[])
    rows = flat("2026-11-23", "2026-11-27")
    rows["2026-11-24"] = (3710.0, 3390.0, 3500.0)  # both in one bar: only the first counts
    r = evaluate(s, CREATED, bars(rows), date(2026, 11, 28))
    assert r.status == "aperta" and r.targets[1]["status"] == "attiva"


def test_spec_validation():
    with pytest.raises(ValueError):
        spec(probability=1.5)
    with pytest.raises(ValueError):
        spec(targets=[{"label": "x", "kind": "touch_above", "zone_low": 10, "zone_high": 5,
                       "deadline": "2027-01-01"}])


def test_weekly_closes():
    b = bars(flat("2026-11-23", "2026-12-04"))
    assert _weekly_closes(b, date(2026, 12, 4)) == {date(2026, 11, 27)}
    assert _weekly_closes(b, date(2026, 12, 5)) == {date(2026, 11, 27), date(2026, 12, 4)}


# ---- stats --------------------------------------------------------------------------------
def test_brier():
    assert brier([(1.0, 1), (0.0, 0)]) == 0
    assert brier([(0.5, 1), (0.5, 0)]) == 0.25
    assert brier([(0.8, 0)]) == pytest.approx(0.64)
    assert brier([]) is None


def test_summarize():
    base = {"asset": "XAUUSD", "author": "yousef", "horizon": "fino a 3 mesi", "tags": ["fed"],
            "targets_hit": 1, "targets_decided": 1}
    rows = [base | {"status": "colpita", "probability": 0.7},
            base | {"status": "invalidata", "probability": 0.6},
            base | {"status": "aperta", "probability": None},
            base | {"status": "scaduta", "probability": None, "asset": "SPY"}]
    s = summarize(rows)
    assert s["overall"]["resolved"] == 3 and s["overall"]["hit_rate"] == pytest.approx(0.333)
    assert s["brier"]["n"] == 2
    assert s["brier"]["score"] == pytest.approx(((0.7 - 1) ** 2 + 0.6**2) / 2, abs=1e-4)
    assert s["by_asset"]["SPY"]["expired"] == 1
    assert s["by_event"]["fed"]["total"] == 4


def test_horizon_bucket():
    assert horizon_bucket(5) == "fino a 1 settimana"
    assert horizon_bucket(71) == "fino a 3 mesi"


# ---- futures-derived spot ----------------------------------------------------------------
def test_contract_calendar():
    dec = Contract("GC", 2026, 12)
    assert dec.symbol == "GCZ26.CMX"
    assert dec.first_notice == date(2026, 11, 30)
    assert dec.last_trade == date(2026, 12, 29)
    assert [c.symbol for c in contracts_from(date(2026, 11, 24), 2)] == ["GCZ26.CMX",
                                                                         "GCG27.CMX"]
    assert [c.symbol for c in contracts_from(date(2026, 11, 25), 2)] == ["GCG27.CMX",
                                                                         "GCJ27.CMX"]


def test_estimate_spot_removes_carry():
    d = pd.Timestamp("2026-11-20")
    near = pd.DataFrame({"open": [3539.0], "high": [3640.0], "low": [3500.0],
                         "close": [3539.0]}, index=[d])
    nxt = near * 1.0081
    out = estimate_spot({"GCZ26.CMX": near, "GCG27.CMX": nxt}, d.date(), d.date())
    # Carry ≈ ln(1.0081)/(57/365); 39 days to Dec expiry
    import math
    c = math.log(1.0081) / (57 / 365)
    assert out["close"].iloc[0] == pytest.approx(3539.0 * math.exp(-c * 39 / 365))
    assert out["low"].iloc[0] < out["close"].iloc[0] < out["high"].iloc[0]
    assert json.loads(out["detail"].iloc[0])["contract"] == "GCZ26.CMX"


def test_estimate_spot_skips_days_without_next_contract():
    d = pd.Timestamp("2026-11-20")
    near = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}, index=[d])
    assert estimate_spot({"GCZ26.CMX": near}, d.date(), d.date()).empty


# ---- service (database) ------------------------------------------------------------------
def test_create_freezes_spec_and_verify_logs_events(session, monkeypatch, tmp_path):
    from app.db import Bar, PredictionEvent
    from app.predictions import service

    monkeypatch.setattr(service, "refresh_bars", lambda *a, **k: 0)
    for d, (h, lo, c) in flat("2026-11-16", "2026-11-27", close=3519.43, spread=10).items():
        session.add(Bar(instrument="XAUUSD_EST", date=date.fromisoformat(d), open=c, high=h,
                        low=lo, close=c, source="test", fetched_at=datetime(2026, 11, 21)))
    session.flush()
    monkeypatch.setattr(service, "ledger_dir", lambda: tmp_path)
    p = service.create(session, spec(), now=datetime(2026, 11, 21, 10))
    assert p.id == "P-0001"
    assert (tmp_path / "P-0001.json").exists()
    assert json.loads(p.context)["instrument_offset"] == pytest.approx(18.44)

    session.get(Bar, 1)  # noqa: B018
    b = session.query(Bar).filter_by(date=date(2026, 11, 25)).one()
    b.high = 3705.0  # + 18.44 → 3723.44 ≥ 3720
    session.flush()
    rep = service.verify(session, as_of=date(2026, 11, 28), refresh=False)
    assert rep[0]["status"] == "aperta"
    assert any("Fase 1" in m for m in rep[0]["new_events"])
    # Running again logs nothing new
    assert service.verify(session, as_of=date(2026, 11, 28), refresh=False)[0]["new_events"] == []
    kinds = [e.kind for e in session.query(PredictionEvent).order_by(PredictionEvent.id)]
    assert kinds == ["created", "target_hit"]

    # Tampering with the stored spec is detected
    p.spec = p.spec.replace("3720", "3700")
    with pytest.raises(RuntimeError):
        service.spec_of(p)


def test_align_refuses_entry_far_from_instrument(session, monkeypatch, tmp_path):
    from app.db import Bar
    from app.predictions import service

    monkeypatch.setattr(service, "refresh_bars", lambda *a, **k: 0)
    session.add(Bar(instrument="XAUUSD_EST", date=date(2026, 11, 20), open=3000, high=3000,
                    low=3000, close=3000, source="test", fetched_at=datetime(2026, 11, 21)))
    session.flush()
    monkeypatch.setattr(service, "ledger_dir", lambda: tmp_path)
    with pytest.raises(ValueError, match="too far"):
        service.create(session, spec(), now=datetime(2026, 11, 21, 10))


def test_ledger_round_trip_keeps_id_and_date(session, monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db import Base, Prediction
    from app.predictions import service

    monkeypatch.setattr(service, "ledger_dir", lambda: tmp_path)
    p = service.create(session, spec(align_to_entry=False), now=datetime(2026, 11, 21, 10))
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as fresh:
        assert service.import_ledger(fresh) == ["P-0001"]
        q = fresh.get(Prediction, "P-0001")
        assert q.created_at == p.created_at and q.spec_hash == p.spec_hash
        assert service.import_ledger(fresh) == []  # idempotent
    # A ledger file edited by hand is refused
    f = tmp_path / "P-0001.json"
    f.write_text(f.read_text(encoding="utf-8").replace("3720", "3700"), encoding="utf-8")
    with Session(eng) as other:
        Base.metadata.drop_all(eng)
        Base.metadata.create_all(eng)
        with pytest.raises(RuntimeError):
            service.import_ledger(other)
