from datetime import date, timedelta

import pytest

from app import catalog
from app.jarvis import demo, scene, tools
from app.jarvis.scene import Script, align, find_word, fold
from app.sources import RawPoint
from app.store import save_points


# ---- alignment -----------------------------------------------------------------------------
def test_fold_keeps_length_and_removes_accents():
    t = "Liquidità è già più alta, M2!"
    assert len(fold(t)) == len(t)
    assert fold(t) == "liquidita e gia piu alta  m2 "


def test_find_word_prefix_and_boundary():
    f = fold("La M2 sta risalendo, poi il dollaro risale")
    assert find_word(f, "risal") == f.index("risalendo")
    assert find_word(f, "salendo") is None  # not at a word start
    assert find_word(f, "M2") == 3
    assert find_word(f, "il dollaro") == f.index("il dollaro")


def test_align_follows_speaking_order_and_repeats():
    s = Script(parlato="L'oro sale. Poi l'oro scende, e l'oro riparte.", scene=[
        {"alla_parola": "oro", "azione": "apri_grafico", "id": "GOLD"},
        {"alla_parola": "oro", "azione": "mostra_livello", "valore": 1},
        {"alla_parola": "riparte", "azione": "chiudi"},
    ])
    pos = [p["char_index"] for p in align(s)]
    assert pos == [2, 18, 38]


def test_align_accents_and_missing_word():
    s = Script(parlato="La liquidità cresce.", scene=[
        {"alla_parola": "LIQUIDITA", "azione": "mostra_regime"},
        {"alla_parola": "inesistente", "azione": "chiudi"},
    ])
    a = align(s)
    assert a[0]["char_index"] == 3 and a[0]["warning"] is None
    assert "non presente" in a[1]["warning"]


def test_script_rejects_unknown_action():
    with pytest.raises(ValueError):
        Script(parlato="x", scene=[{"alla_parola": "x", "azione": "esplodi"}])


def test_estimate_times():
    assert scene.estimate_times("x" * 140, [0, 70, 140]) == [0.0, 5.0, 10.0]


# ---- tools and director on a small database ----------------------------------------------
@pytest.fixture
def seeded(session):
    today = date.today()
    pts = [RawPoint(today - timedelta(days=30 * i), 3000 + 10 * i, today - timedelta(days=30 * i))
           for i in range(40)]
    save_points(session, catalog.get("GOLD"), pts, "market_close")
    m2 = [RawPoint(today - timedelta(days=30 * i), 20000 + 50 * (40 - i)) for i in range(40)]
    save_points(session, catalog.get("M2SL"), m2, "first_seen", today=today)
    return session


def test_query_serie(seeded):
    r = tools.query_serie(seeded, "GOLD", "1y")
    assert r["unita"] == "USD/oncia" and r["ultimo"]["valore"] == 3000
    assert r["massimo"]["valore"] >= r["minimo"]["valore"]
    assert all(p["data"] >= (date.today() - timedelta(days=365)).isoformat() for p in r["punti"])
    assert r["fonti"] == ["yahoo:GC=F"]


def test_query_serie_bad_input_is_returned_as_error(seeded):
    assert "sconosciuta" in tools.call(seeded, "query_serie", {"id": "NOPE"})["errore"]
    assert "periodo" in tools.call(seeded, "query_serie", {"id": "GOLD", "periodo": "7y"})["errore"]
    assert "argomenti" in tools.call(seeded, "query_serie", {"wrong": 1})["errore"]
    assert "sconosciuto" in tools.call(seeded, "boh", {})["errore"]


def test_downsample_keeps_last_point():
    import pandas as pd

    df = pd.DataFrame({"value": range(1000)}, index=pd.date_range("2020-01-01", periods=1000))
    d = tools._downsample(df, 100)
    assert len(d) <= 101 and d.index[-1] == df.index[-1]


def test_tool_schemas_are_well_formed():
    for t in tools.TOOLS:
        s = t.schema()
        assert set(s) == {"name", "description", "input_schema"}
        assert s["input_schema"]["type"] == "object"
        for r in s["input_schema"].get("required", []):
            assert r in s["input_schema"]["properties"]


def test_registra_previsione_needs_confirmation(seeded):
    spec = {"asset": "SPY", "title": "t", "direction": "long", "entry_price": 500,
            "reasoning": "r", "targets": [{"label": "a", "kind": "touch_above",
                                           "zone_low": 550, "zone_high": 550,
                                           "deadline": "2099-01-01"}]}
    r = tools.call(seeded, "registra_previsione", {"previsione": spec})
    assert r["registrata"] is False and r["anteprima"]["author"] == "jarvis"
    bad = tools.call(seeded, "registra_previsione", {"previsione": {"asset": "SPY"}})
    assert "non valida" in bad["errore"]


def test_direct_attaches_series_data(seeded):
    out = scene.direct(seeded, {"parlato": "L'oro e la M2.", "scene": [
        {"alla_parola": "oro", "azione": "apri_grafico", "id": "GOLD", "periodo": "1y"},
        {"alla_parola": "M2", "azione": "sovrapponi", "id": "M2SL", "su": "GOLD"},
        {"alla_parola": "M2", "azione": "apri_grafico", "id": "NOPE"},
    ]})
    c = out["scene"]
    assert c[0]["dati"]["serie"]["id"] == "GOLD" and c[0]["parametri"]["periodo"] == "1y"
    assert c[1]["dati"]["serie"]["id"] == "M2SL"
    assert "errore" in c[2]["dati"]
    assert out["tempi_stimati"][0] < out["tempi_stimati"][1]


def test_correlation(seeded):
    r = scene.correlation(seeded, "M2SL", "GOLD", 0, "5y")
    assert r["valore"] is not None and -1 <= r["valore"] <= 1
    assert r["mesi"] >= 12


# ---- demo brain ------------------------------------------------------------------------------
def test_it_formatting():
    assert demo.it_num(3537.87, 2) == "3.537,87"
    assert demo.it_num(-13.2, 1) == "-13,2"
    assert demo.it_date("2026-11-20") == "20 novembre 2026"
    assert demo.it_month("2026-09-01") == "settembre 2026"


@pytest.mark.parametrize("q,intent", [
    ("Come sta l'oro?", "gold"), ("qual è il regime", "regime"),
    ("ci sono divergenze?", "scenarios"), ("la M2 sale?", "liquidity"),
    ("dati sul lavoro", "labour"), ("il mio scenario", "predictions_intent"),
    ("ciao", "greeting"), ("che tempo fa", "fallback"),
])
def test_demo_routing(monkeypatch, q, intent):
    for _, fn in demo.INTENTS:
        monkeypatch.setattr(demo, fn.__name__, fn)
    patched = [(p, (lambda s, n=fn.__name__: {"parlato": n, "scene": []})) for p, fn in
               demo.INTENTS]
    monkeypatch.setattr(demo, "INTENTS", patched)
    monkeypatch.setattr(demo, "fallback", lambda s: {"parlato": "fallback", "scene": []})
    a = demo.answer(None, q)
    assert a["parlato"] == intent and a["modalita"] == "dimostrativa"


def test_demo_gold_uses_database_numbers(seeded):
    a = demo.gold(seeded)
    assert "3.000 dollari" in a["parlato"]
    assert "massimo storico di chiusura, 3.390" in a["parlato"]
    out = scene.direct(seeded, a)
    assert [c["warning"] for c in out["scene"]] == [None] * len(out["scene"])


# ---- WebSocket -------------------------------------------------------------------------------
def test_websocket_protocol(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setattr(main, "_ask", lambda t: {"parlato": f"eco: {t}", "scene": []})
    monkeypatch.setattr(main, "start_scheduler", lambda: None)
    with TestClient(main.app) as client, client.websocket_connect("/ws/jarvis") as ws:
        ws.send_json({"tipo": "domanda", "testo": "oro"})
        assert ws.receive_json() == {"tipo": "stato", "stato": "elaboro"}
        r = ws.receive_json()
        assert r["tipo"] == "risposta" and r["parlato"] == "eco: oro"
        ws.send_json({"tipo": "boh"})
        assert ws.receive_json()["tipo"] == "errore"
