import pandas as pd
import pytest

from app.institutions import analysis as A
from app.institutions import config as C
from app.sources.sec13f import normalize_units, parse_infotable

XML = b"""<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
<cusip>037833100</cusip><value>1000</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt>
<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
<cusip>037833100</cusip><value>500</value><shrsOrPrnAmt><sshPrnamt>5</sshPrnamt>
<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>CALL</titleOfClass>
<cusip>037833100</cusip><value>300</value><shrsOrPrnAmt><sshPrnamt>3</sshPrnamt>
<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Call</putCall></infoTable>
</informationTable>"""


def frame(rows):
    return pd.DataFrame([{"cusip": c, "issuer": n, "classe": "COM", "put_call": "", "tipo": "SH",
                          "valore": q * px, "quantita": q} for c, n, q, px in rows])


def test_parse_sums_rows_and_keeps_options_apart():
    df = parse_infotable(XML)
    sh = df[df.put_call == ""].iloc[0]
    assert sh.quantita == 15 and sh.valore == 1500
    assert (df.put_call == "Call").sum() == 1


def test_values_in_thousands_are_converted():
    df = frame([("X", "A", 100, 0.05), ("Y", "B", 10, 0.2)])  # implied price < $1
    assert normalize_units(df)["valore"].tolist() == [5000, 2000]
    ok = frame([("X", "A", 100, 50.0)])
    assert normalize_units(ok)["valore"].tolist() == [5000]


def test_changes_classify_moves():
    prev = frame([("A", "ALPHA", 100, 10), ("B", "BETA", 100, 10), ("C", "GAMMA", 100, 10),
                  ("D", "DELTA", 100, 10)])
    curr = frame([("A", "ALPHA", 200, 10), ("B", "BETA", 50, 10), ("D", "DELTA", 100, 10),
                  ("E", "EPS", 30, 10)])
    ch = A.changes(prev, curr)
    assert ch.loc["A", "tipo"] == "aumentata" and ch.loc["A", "variazione_valore"] == 1000
    assert ch.loc["B", "tipo"] == "ridotta"
    assert ch.loc["C", "tipo"] == "venduta" and ch.loc["C", "variazione_valore"] == -1000
    assert ch.loc["D", "tipo"] == "invariata" and ch.loc["E", "tipo"] == "nuova"
    assert ch["peso"].sum() == pytest.approx(1)


def test_cusip_change_is_not_a_sale_plus_a_buy():
    prev = frame([("OLD", "EXXON MOBIL CORP", 1000, 100)])
    curr = frame([("NEW", "EXXONMOBIL HOLDINGS CO", 1100, 100)])
    ch = A.changes(prev, curr)
    assert ch.loc["OLD", "tipo"] == "cambio di codice"
    assert ch.loc["NEW", "tipo"] == "aumentata poco"  # +10% on top of the old shares
    assert ch.loc["NEW", "variazione_quote"] == 100


def test_price_context_uses_the_quarter_average():
    idx = pd.bdate_range("2026-06-01", "2026-11-20")
    s = pd.Series(100.0, index=idx)
    s[(idx > "2026-06-30") & (idx <= "2026-09-30")] = 50.0
    s[idx > "2026-09-30"] = 60.0
    p = A.price_context(s, pd.Timestamp("2026-09-30"))
    assert p["prezzo_medio_trimestre"] == 50 and p["prezzo_oggi"] == 60
    assert p["da_prezzo_medio"] == pytest.approx(0.2)


def test_regime_fit_sums_favouring_quadrants():
    probs = {"A": .3, "B": .5, "C": .1, "D": .1}
    sectors = {"A": ["Technology"], "B": ["Energy"], "C": ["Energy"], "D": []}
    assert A.regime_fit("Energy", probs, sectors) == pytest.approx(0.6)
    assert A.regime_fit("Utilities", probs, sectors) == 0
    assert A.regime_fit(None, probs, sectors) is None


def test_verdict_labels():
    good_q = {"controlli": {}, "superati": 3, "su": 3}
    assert A.verdict(0.02, 0.6, good_q, 1, "aumentata")["giudizio"] == "margine"
    assert A.verdict(0.40, 0.6, good_q, 2, "nuova")["giudizio"] == "treno passato"
    assert A.verdict(0.02, 0.1, None, 1, "nuova")["giudizio"] == "contro il regime"
    v = A.verdict(None, None, None, 1, "nuova")
    assert v["giudizio"] == "da seguire" and any("non disponibile" in m for m in v["motivi"])


def test_quality_counts_only_known_checks():
    q = A.quality({"roe": 0.2, "debito_patrimonio": None, "pe_atteso": 40})
    assert (q["superati"], q["su"]) == (1, 2)
    assert C.MIN_ROE == 0.15


def test_latest_due_quarter():
    assert A.latest_due_quarter(pd.Timestamp("2026-11-22")) == pd.Timestamp("2026-09-30")
    assert A.latest_due_quarter(pd.Timestamp("2026-11-10")) == pd.Timestamp("2026-06-30")
    assert A.latest_due_quarter(pd.Timestamp("2026-02-15")) == pd.Timestamp("2025-12-31")


def test_amendments_restate_or_add():
    from app.sources.sec13f import Filing, SecClient

    class Fake(SecClient):
        def __init__(self):
            self.data = {"1": frame([("A", "ALPHA", 10, 10)]), "2": frame([("B", "BETA", 5, 10)]),
                         "3": frame([("C", "GAMMA", 1, 10)])}
            self.types = {"2": "NEW HOLDINGS", "3": "RESTATEMENT"}

        def holdings(self, f):
            return self.data[f.accession]

        def amendment_type(self, f):
            return self.types[f.accession]

    f1 = Filing(1, "1", "13F-HR", "2026-08-14", "2026-06-30")
    f2 = Filing(1, "2", "13F-HR/A", "2026-11-16", "2026-06-30")
    f3 = Filing(1, "3", "13F-HR/A", "2026-11-20", "2026-06-30")
    sec = Fake()
    assert set(sec.period_holdings([f1, f2], "2026-06-30")["cusip"]) == {"A", "B"}
    assert set(sec.period_holdings([f1, f2, f3], "2026-06-30")["cusip"]) == {"C"}


def test_split_is_not_a_purchase():
    prev = frame([("S", "SPLITCO", 100, 300.0)])
    curr = frame([("S", "SPLITCO", 330, 100.0)])  # 3-for-1 split, then +10% shares
    ch = A.changes(prev, curr, splits={"S": 3})
    assert ch.loc["S", "frazionamento"] == 3
    assert ch.loc["S", "prima"] == 300 and ch.loc["S", "tipo"] == "aumentata poco"
    assert A.changes(prev, curr).loc["S", "tipo"] == "aumentata"  # no split known


def test_dcf_matches_a_hand_computation():
    # constant growth = terminal: PV of a growing perpetuity = fcf(1+g)/(r-g)
    v = A.dcf(100, 10, 0, 0, 0.02, 0.08, 0.02, years=10)
    assert v == pytest.approx(100 * 1.02 / 0.06 / 10, rel=1e-9)
    assert A.dcf(-5, 10, 0, 0, 0.05, 0.08, 0.02) is None
    assert A.dcf(100, 10, 50, 0, 0.02, 0.08, 0.02) == pytest.approx(v + 5)


def test_buffett_margin_of_safety():
    from app.rqe.config import SCREENER

    info = {"fcf": 100.0, "azioni": 10.0, "cassa": 0, "debito": 0, "crescita_utili": 0.05,
            "roe": 0.2, "ebitda": 150.0, "margine_operativo": 0.3, "pe": 10}
    cheap = A.buffett(info, price=50, ten_year=0.04, rules=SCREENER)
    assert cheap["tasso_sconto"] == pytest.approx(0.09)
    assert cheap["scenari"]["base"]["margine"] > 0.25
    assert cheap["superati"] == cheap["su"]
    dear = A.buffett(info, price=10_000, ten_year=0.04, rules=SCREENER)
    assert dear["scenari"]["base"]["margine"] < 0 and "caro" in dear["sintesi"]


def test_sector_by_regime_uses_the_previous_month_regime():
    idx = pd.date_range("2020-01-31", periods=4, freq="ME")
    regimes = pd.Series(["A", "B", "A", "B"], index=idx)
    excess = pd.Series([9.0, 0.01, 0.02, 0.03], index=idx)  # Jan has no known regime before it
    out = A.sector_by_regime(excess, regimes)
    assert out["A"]["mesi"] == 2 and out["A"]["eccesso_annuo"] == pytest.approx((0.01 + 0.03) / 2 * 12)
    assert out["B"]["mesi"] == 1 and out["B"]["eccesso_annuo"] == pytest.approx(0.24)
