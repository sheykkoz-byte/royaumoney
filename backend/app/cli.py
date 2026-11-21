"""Command line: python -m app.cli {verify,ingest,health}."""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

from app.config import BACKEND_DIR, get_settings
from app.db import init_db, session_scope
from app.health import data_health
from app.ingest import run_all, verify_fred
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


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="Check every FRED ID and unit, write docs/serie-verificate.md")
    ing = sub.add_parser("ingest", help="Download and store data")
    ing.add_argument("--full", action="store_true", help="Re-download the whole history")
    ing.add_argument("--source", choices=["all", "fred", "yahoo"], default="all")
    sub.add_parser("health", help="Print data freshness")
    args = p.parse_args()

    init_db()
    settings = get_settings()
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
