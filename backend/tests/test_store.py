from datetime import date

from sqlalchemy import select

from app import catalog
from app.db import Observation
from app.sources import RawPoint
from app.store import load_frame, save_points

M2 = catalog.get("M2SL")  # monthly, lag 55, scale 1
WALCL = catalog.get("WALCL")  # millions -> billions


def versions(session, sid):
    return session.execute(
        select(Observation.ref_date, Observation.published_at, Observation.value,
               Observation.pub_method)
        .where(Observation.series_id == sid)
        .order_by(Observation.ref_date, Observation.published_at)
    ).all()


def test_scale_is_applied_and_raw_kept(session):
    save_points(session, WALCL, [RawPoint(date(2026, 11, 18), 6_741_452)], "first_seen",
                today=date(2026, 11, 21))
    row = session.scalars(select(Observation)).one()
    assert row.value == 6741.452
    assert row.raw_value == 6_741_452
    assert row.unit == "Miliardi di USD"


def test_bulk_history_gets_estimated_publication_date(session):
    rep = save_points(session, M2, [RawPoint(date(2026, 8, 1), 100.0),
                                    RawPoint(date(2026, 9, 1), 101.0)],
                      "first_seen", today=date(2026, 11, 21))
    assert rep.inserted == 2
    v = versions(session, "M2SL")
    assert v[0].published_at == date(2026, 9, 25)  # 1 Aug + 55 days
    assert v[0].pub_method == "estimated_lag"


def test_estimated_date_never_in_the_future(session):
    save_points(session, M2, [RawPoint(date(2026, 11, 1), 1.0)], "first_seen",
                today=date(2026, 11, 21))
    assert versions(session, "M2SL")[0].published_at == date(2026, 11, 21)


def test_new_dates_after_history_are_first_seen_today(session):
    save_points(session, M2, [RawPoint(date(2026, 9, 1), 101.0)], "x", today=date(2026, 11, 1))
    save_points(session, M2, [RawPoint(date(2026, 9, 1), 101.0),
                              RawPoint(date(2026, 10, 1), 102.0)], "x", today=date(2026, 11, 25))
    v = versions(session, "M2SL")
    assert (v[-1].ref_date, v[-1].published_at, v[-1].pub_method) == (
        date(2026, 10, 1), date(2026, 11, 25), "first_seen")


def test_revision_adds_a_version_and_keeps_the_old_one(session):
    save_points(session, M2, [RawPoint(date(2026, 9, 1), 101.0)], "x", today=date(2026, 11, 1))
    rep = save_points(session, M2, [RawPoint(date(2026, 9, 1), 101.5)], "x",
                      today=date(2026, 11, 25))
    assert rep.revised == 1
    v = versions(session, "M2SL")
    assert [x.value for x in v] == [101.0, 101.5]
    # Point in time: before the revision we see the old value
    assert load_frame(session, "M2SL", as_of=date(2026, 11, 24))["value"].iloc[0] == 101.0
    assert load_frame(session, "M2SL")["value"].iloc[0] == 101.5


def test_unchanged_value_adds_nothing(session):
    pts = [RawPoint(date(2026, 9, 1), 101.0)]
    save_points(session, M2, pts, "x", today=date(2026, 11, 1))
    rep = save_points(session, M2, pts, "x", today=date(2026, 11, 2))
    assert rep.unchanged == 1 and len(versions(session, "M2SL")) == 1


def test_alfred_vintages_store_only_real_changes(session):
    d = date(2026, 6, 1)
    pts = [RawPoint(d, 100.0, date(2026, 7, 25)),
           RawPoint(d, 100.0, date(2026, 8, 22)),  # reissued unchanged
           RawPoint(d, 100.4, date(2026, 9, 26))]
    rep = save_points(session, M2, pts, "alfred")
    assert (rep.inserted, rep.revised, rep.unchanged) == (1, 1, 1)
    # Same vintages again: nothing new
    rep2 = save_points(session, M2, pts, "alfred")
    assert rep2.unchanged == 3
    assert load_frame(session, "M2SL", as_of=date(2026, 7, 24)).empty
    assert load_frame(session, "M2SL", as_of=date(2026, 8, 30))["value"].iloc[0] == 100.0


def test_same_day_market_price_updates_in_place(session):
    gold = catalog.get("GOLD")
    d = date(2026, 11, 20)
    save_points(session, gold, [RawPoint(d, 3550.0, d)], "market_close")
    rep = save_points(session, gold, [RawPoint(d, 3539.0, d)], "market_close")
    assert rep.updated == 1
    assert [x.value for x in versions(session, "GOLD")] == [3539.0]
