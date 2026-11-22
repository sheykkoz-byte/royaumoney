from app.cabina import SECTIONS
from app.cabina_guide import MEANING, explain


def tile(id_, section, label, value, state="neutro", reading="", changes=None, decimals=2):
    return {"id": id_, "section": section, "label": label, "value": value, "state": state,
            "reading": reading, "changes": changes or {}, "decimals": decimals}


def test_every_section_has_an_explanation_and_every_tile_a_meaning():
    from app.cabina import METRICS

    tiles = [tile(m.id, m.section, m.label, 1.0) for m in METRICS]
    out = explain(SECTIONS, tiles)
    assert set(out) == set(SECTIONS)
    for sec in SECTIONS:
        assert len(out[sec]["cosa_misura"]) > 100
    assert {m.id for m in METRICS} <= set(MEANING)


def test_rates_reading_uses_the_numbers():
    tiles = [
        tile("DFF", "Tassi", "Fed funds", 3.88, reading="Fed in rialzo: +25 punti base in 3 mesi."),
        tile("DGS2", "Tassi", "Treasury 2 anni", 4.76),
        tile("DGS10", "Tassi", "Treasury 10 anni", 5.04, changes={"1m": -0.11}),
        tile("T10Y2Y", "Tassi", "Curva", 0.29, "verde", "Curva positiva."),
    ]
    oggi = explain(["Tassi"], tiles)["Tassi"]["oggi"]
    assert "il mercato si aspetta altri rialzi" in oggi[1]
    assert "5,04%" in oggi[2] and "-11 punti base" in oggi[2]
    assert explain(["Tassi"], tiles)["Tassi"]["semafori"] == "Semafori: 1 verde."


def test_risk_summary_when_fear_is_only_on_stocks():
    tiles = [tile("VIX", "Dollaro e rischio", "VIX", 35.9, "rosso", "Paura sull'azionario."),
             tile("BAMLH0A0HYM2", "Dollaro e rischio", "HY", 3.52, "verde", "Credito tranquillo.")]
    oggi = explain(["Dollaro e rischio"], tiles)["Dollaro e rischio"]["oggi"]
    assert any("il credito non la conferma" in f for f in oggi)


def test_tiles_with_errors_are_skipped():
    tiles = [{"id": "GOLD", "section": "Materie prime", "label": "Oro", "errore": "x"}]
    assert explain(["Materie prime"], tiles)["Materie prime"]["oggi"] == []


def test_scale_zone_at_the_measured_value_matches_the_tile_colour():
    """The explanation window's scale must agree with the traffic light."""
    import numpy as np
    import pandas as pd

    from app.cabina import RULES, scale

    rng = np.random.default_rng(7)
    idx = pd.date_range("2023-01-01", periods=1100, freq="D")
    checked = 0
    for rule in RULES:
        for level in (-2.0, 0.1, 1.5, 3.0, 5.0, 30.0, 200.0):
            s = pd.Series(level + np.cumsum(rng.normal(0, 0.02 * (abs(level) + 1), len(idx))),
                          index=idx)
            if rule in ("sahm", "payrolls", "claims", "m2", "inflation"):
                s = s.resample("MS").last() if rule != "claims" else s.resample("W-SAT").last()
                s = s.abs() + 0.1 if rule == "claims" else s
            v = float(s.iloc[-1])
            state, _ = RULES[rule](s, v)
            sc = scale(rule, s, v)
            if sc is None:
                continue
            m = sc["valore"]
            zone = next(z for z in sc["zone"]
                        if (z["da"] is None or m >= z["da"]) and (z["a"] is None or m < z["a"]))
            assert zone["stato"] == state, (rule, level, m, zone, state)
            checked += 1
    assert checked > 40
