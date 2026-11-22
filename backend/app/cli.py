"""Command line: python -m app.cli {verify,ingest,health}."""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

from app.analysis.engine import run as run_analysis
from app.config import BACKEND_DIR, get_settings
from app.db import Prediction, init_db, session_scope
from app.health import data_health
from app.ingest import run_all, verify_fred
from app.predictions import service as predictions
from app.predictions.spec import PredictionSpec
from app.predictions.stats import track_record
from app.sources.fred import FredClient

DOC = BACKEND_DIR.parent / "docs" / "serie-verificate.md"


def write_verification_doc(results: list[dict], mode: str, path: Path = DOC) -> None:
    lines = [
        "# Serie FRED verificate",
        "",
        f"Generato da `python -m app.cli verify` il {date.today().isoformat()} "
        f"(modalità: {mode}).",
        "",
        "| ID | Titolo su FRED | Unità su FRED | Frequenza | Salvata come | Fattore | Esito |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        esito = "OK" if not r["error"] else f"⚠️ {r['error']}"
        lines.append(
            f"| `{r['id']}` | {r['title'] or '—'} | {r['unit'] or '—'} | {r['frequency'] or '—'} "
            f"| {r['stored_unit']} | ×{r['scale']:g} | {esito} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(x, nd=2, sign=True) -> str:
    if x is None:
        return "—"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def print_analysis(r: dict) -> None:
    g = r["regime"]
    print(f"\nANALISI AL {r['as_of']}\n")
    if g.get("available"):
        print(f"REGIME: {g['name']}")
        if g["borderline_axes"]:
            print(f"  al confine: {', '.join(g['borderline_axes'])}")
    for ax in g["axes"].values():
        comps = ", ".join(f"{c['label']} {_fmt(c['scaled'])}" for c in ax["components"])
        print(f"  {ax['label']:<11} {_fmt(ax['score']):>6}  ({comps})")
    cur = (g.get("history") or {}).get("current")
    if cur:
        print(f"\n  Nei {cur['months']} mesi passati in questo regime (rispetto alla media):")
        best, worst = cur["assets"][:3], cur["assets"][-3:]
        print("   meglio: " + ", ".join(f"{a['name']} {_fmt(a['vs_all_months_pct'])}%"
                                        for a in best))
        print("   peggio: " + ", ".join(f"{a['name']} {_fmt(a['vs_all_months_pct'])}%"
                                        for a in worst))
    print("\nSCENARI           punteggio  macro  mercato  convergenza")
    for sc in r["scenarios"]:
        alarm = "  ⚠ DIVERGENZA" if sc["divergence_alarm"] else ""
        print(f"  {sc['name']:<20} {sc['score']:>5}  {_fmt(sc['macro_voice']):>6} "
              f"{_fmt(sc['market_voice']):>7}  {sc['convergence']:>6}{alarm}")
    print(f"\n{r['verdict']['text']}")
    top = r["scenarios"][0]
    print(f"\n{top['name']} — a favore:")
    for e in top["supports"][:5]:
        print(f"  + {e['label']} ({e['measure']}): {e['value']} {e['unit']}, z {_fmt(e['z'])}")
    print("contro:")
    for e in top["contradicts"][:5]:
        print(f"  − {e['label']} ({e['measure']}): {e['value']} {e['unit']}, z {_fmt(e['z'])}")
    for d in r["divergences"]:
        print(f"\n⚠ {d['text']} (distanza {d['gap']}σ, più ampia del "
              f"{d['percentile']:.0%} dei mesi passati)")
    for n in r["notes"]:
        print(f"\nNota: {n}")


def print_prediction(v: dict) -> None:
    print(f"\n{v['id']} · {v['title']}")
    print(f"  {v['asset']} ({v['instrument_label']}), ingresso {v['entry_price']}, "
          f"autore {v['author']}, registrata {v['created_at']}")
    if v.get("annulment"):
        a = v["annulment"]
        print(f"  ANNULLATA il {a['at']}: {a['reason']}"
              + (f" → sostituita da {a['replaced_by']}" if a.get("replaced_by") else ""))
    if v.get("instrument_offset"):
        print(f"  allineamento allo strumento: {v['instrument_offset']:+.2f}")
    print(f"  STATO: {v['status'].upper()}"
          + (f" il {v['resolved_on']}" if v["resolved_on"] else "")
          + f" · ultimo prezzo verificato: {v['last_bar_date'] or '—'}")
    for t in v["targets"]:
        print(f"  [{t.get('status', '')}] {t['label']}: tocca {t.get('trigger')} "
              f"entro {t['deadline']}" + (f" → {t['hit_on']} a {t['hit_price']}"
                                          if t.get("hit_on") else ""))
    for r in v["invalidations"]:
        print(f"  invalidazione: {r['description']}"
              + (f" → SCATTATA {r['triggered_on']}" if r.get("triggered_on") else ""))
    if v.get("extremes"):
        e = v["extremes"]
        print(f"  dalla registrazione: massimo {e['high']} ({e['high_on']}), "
              f"minimo {e['low']} ({e['low_on']}), ultima chiusura {e['last_close']}")
    if v.get("context", {}).get("regime"):
        print(f"  contesto alla registrazione: {v['context']['regime']}. "
              f"{v['context'].get('verdict', '')}")
    for ev in v.get("events", []):
        print(f"  {ev['date']}  {ev['message']}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="Check every FRED ID and unit, write docs/serie-verificate.md")
    ing = sub.add_parser("ingest", help="Download and store data")
    ing.add_argument("--full", action="store_true", help="Re-download the whole history")
    ing.add_argument("--source", choices=["all", "fred", "yahoo"], default="all")
    sub.add_parser("health", help="Print data freshness")
    an = sub.add_parser("analisi", help="Regime, scenarios and convergence")
    an.add_argument("--as-of", type=date.fromisoformat, default=None,
                    help="Point-in-time analysis on this date (YYYY-MM-DD)")
    an.add_argument("--json", action="store_true", help="Print the full JSON")
    pv = sub.add_parser("previsioni", help="Prediction registry")
    pvs = pv.add_subparsers(dest="action", required=True)
    add = pvs.add_parser("add", help="Register a prediction from a JSON file")
    add.add_argument("file", type=Path)
    ver = pvs.add_parser("verifica", help="Check open predictions against prices")
    ver.add_argument("--as-of", type=date.fromisoformat, default=None)
    pvs.add_parser("list", help="All predictions with their state")
    pvs.add_parser("importa", help="Load registro/*.json into the database (keeps dates)")
    cyc = pvs.add_parser("ciclo", help="Daily job: import ledger, verify, write state")
    cyc.add_argument("--as-of", type=date.fromisoformat, default=None)
    ann = pvs.add_parser("annulla", help="Withdraw a prediction before any later price exists")
    ann.add_argument("id")
    ann.add_argument("--motivo", required=True)
    ann.add_argument("--sostituita-da", default=None)
    show = pvs.add_parser("show", help="One prediction with its event log")
    show.add_argument("id")
    sub.add_parser("track-record", help="Hit rates and Brier score")
    sub.add_parser("rqe", help="Regime & Quality Engine: write frontend/public/rqe/rqe.json")
    sub.add_parser("rqe-taratura", help="Calibrate the regime tilt (train 2000-2012, test 2013+)")
    sub.add_parser("cabina", help="Write the cockpit's macro board (frontend/public/cabina)")
    args = p.parse_args()

    init_db()
    settings = get_settings()
    if args.cmd == "cabina":
        from app import cabina

        with session_scope() as s:
            print(f"written {cabina.export(s)}")
        return
    if args.cmd == "verify":
        mode = "API FRED" if settings.fred_api_key else "pagine pubbliche FRED (senza chiave)"
        with session_scope() as s:
            res = verify_fred(s, FredClient(settings.fred_api_key))
        write_verification_doc(res, mode)
        bad = [r for r in res if r["error"]]
        for r in res:
            print(f"{'OK ' if not r['error'] else 'ERR'} {r['id']:<14} {r['unit']}"
                  + (f"  ← {r['error']}" if r["error"] else ""))
        print(f"\n{len(res) - len(bad)}/{len(res)} OK · written {DOC}")
    elif args.cmd == "ingest":
        sources = ("fred", "yahoo") if args.source == "all" else (args.source,)
        report = run_all(full=args.full, sources=sources)
        print(json.dumps(report, indent=1, default=str))
    elif args.cmd == "analisi":
        with session_scope() as s:
            r = run_analysis(s, args.as_of, has_fred_key=bool(settings.fred_api_key))
        if args.json:
            print(json.dumps(r, indent=1, ensure_ascii=False))
        else:
            print_analysis(r)
    elif args.cmd == "previsioni":
        with session_scope() as s:
            if args.action == "add":
                spec = PredictionSpec.model_validate_json(args.file.read_text(encoding="utf-8"))
                p = predictions.create(s, spec, predictions.analysis_context(s))
                predictions.verify(s, ids=[p.id])
                print(f"Registrata {p.id} · impronta {p.spec_hash[:16]}…")
                print_prediction(predictions.view(s, p))
            elif args.action == "verifica":
                for r in predictions.verify(s, as_of=args.as_of):
                    print(f"{r['id']}: {r.get('status')} (ultimo prezzo {r.get('last_bar')})"
                          + (f" ⚠ {r['error']}" if r.get("error") else ""))
                    for m in r.get("new_events", []):
                        print(f"  · {m}")
            elif args.action == "importa":
                added = predictions.import_ledger(s)
                print(f"Importate: {', '.join(added) or 'nessuna (già presenti)'}")
                if added:
                    predictions.verify(s, ids=added)
            elif args.action == "ciclo":
                report = predictions.daily_cycle(s, args.as_of)
                for r in report:
                    print(f"{r['id']}: {r.get('status')} (ultimo prezzo {r.get('last_bar')})"
                          + (f" ⚠ {r['error']}" if r.get("error") else ""))
                    for m in r.get("new_events", []):
                        print(f"  · {m}")
                if any(r.get("error") for r in report):
                    raise SystemExit(2)
            elif args.action == "annulla":
                p = predictions.annul(s, args.id, args.motivo, args.sostituita_da)
                print(f"{p.id} annullata.")
            elif args.action == "list":
                for v in predictions.list_predictions(s):
                    print(f"{v['id']}  {v['status']:<10} {v['asset']:<7} {v['title']}")
            elif args.action == "show":
                p = s.get(Prediction, args.id)
                if p is None:
                    raise SystemExit(f"{args.id} non trovata")
                print_prediction(predictions.view(s, p))
    elif args.cmd == "rqe":
        from app.rqe import service as rqe

        with session_scope() as s:
            path = rqe.export(s)
        snap = json.loads(path.read_text(encoding="utf-8"))
        r = snap["regime"]
        print(f"Regime: {r.get('nome')} · " + " ".join(
            f"{q} {p:.0%}" for q, p in (r.get("probabilita") or {}).items()))
        for k, v in snap["backtest"]["statistiche"].items():
            print(f"  {k:<8} CAGR {v['cagr']:.1%}  vol {v['volatilita']:.1%}  "
                  f"Sharpe {v['sharpe']}  max DD {v['max_drawdown']:.1%}")
        print(f"written {path}")
    elif args.cmd == "rqe-taratura":
        from app.rqe import service as rqe

        with session_scope() as s:
            sm = rqe.calibrate_and_save(s)
        print("scelto sul periodo di taratura:", sm["scelto"])
        print("risk parity  :", sm["risk_parity"]["test"])
        print("con il tilt  :", sm["scelto_stats"]["test"])
        print("significatività (verifica):", sm["significativita_test"])
    elif args.cmd == "track-record":
        with session_scope() as s:
            print(json.dumps(track_record(s), indent=1, ensure_ascii=False))
    elif args.cmd == "health":
        with session_scope() as s:
            h = data_health(s)
        icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
        print(f"{icon[h['status']]} {h['counts']}")
        for i in h["series"]:
            print(f"{icon[i['status']]} {i['id']:<15} last {i['last_ref_date'] or '—':<10} "
                  f"age {str(i['age_days']) + 'd' if i['age_days'] is not None else '—':>5} "
                  f"(max {i['max_age_days']}d)  {i['error'] or ''}")


if __name__ == "__main__":
    main()
