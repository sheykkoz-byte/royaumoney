from datetime import date

import pytest

from app import catalog
from app.health import data_health, status_for
from app.sources import RawPoint
from app.sources.fred import FredError, parse_csv, parse_series_page
from app.store import save_points


def test_parse_csv_skips_missing_values():
    text = "observation_date,DGS10\n2026-11-18,5.01\n2026-11-19,.\n2026-11-20,5.04\n"
    pts = parse_csv(text, "DGS10")
    assert [(p.ref_date.day, p.value) for p in pts] == [(18, 5.01), (20, 5.04)]


def test_parse_csv_rejects_wrong_series():
    with pytest.raises(FredError):
        parse_csv("observation_date,DGS2\n2026-11-20,4.7\n", "DGS10")


def test_parse_series_page_reads_units():
    page = (
        "<html><head><title>Bank of Japan: Total Assets for Japan (JPNASSETS) | FRED | "
        "St. Louis Fed</title></head><body><span>Units:</span>&nbsp; <span>100 Million Yen,"
        "</span> Not Seasonally Adjusted <span>Frequency:</span>&nbsp; Monthly, End of Period"
        "<script>WebFontConfig</script></body></html>"
    )
    m = parse_series_page(page, "JPNASSETS")
    assert m.unit == "100 Million Yen"
    assert m.title.startswith("Bank of Japan")
    assert m.frequency.startswith("Monthly")


@pytest.mark.parametrize("age,expected", [(None, "red"), (3, "green"), (5, "green"),
                                          (7, "yellow"), (8, "red")])
def test_status_thresholds(age, expected):
    assert status_for(age, 5) == expected


def test_data_health_reports_age_and_missing(session):
    d = date(2026, 11, 20)
    save_points(session, catalog.get("GOLD"), [RawPoint(d, 3539.0, d)], "market_close")
    h = data_health(session, today=date(2026, 11, 21))
    by_id = {i["id"]: i for i in h["series"]}
    assert by_id["GOLD"]["status"] == "green"
    assert by_id["GOLD"]["age_days"] == 1
    assert by_id["M2SL"]["status"] == "red"  # never downloaded
    assert h["status"] == "red"
    assert len(h["series"]) == len(catalog.SERIES)


def test_catalog_ids_are_unique_and_derived_inputs_exist():
    ids = [s.id for s in catalog.SERIES]
    assert len(ids) == len(set(ids))
    for s in catalog.SERIES:
        for i in s.inputs:
            assert i in catalog.BY_ID, f"{s.id} needs unknown input {i}"
