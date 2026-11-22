"""Record what Jarvis's tools return, for the artifact's Claude brain (no backend there).

Run from backend/:  uv run python ../frontend/artifact/record_data.py OUT/data.json

Every number the artifact shows or lets Claude say comes from this file, which comes
from the same tools the backend brain calls (app/jarvis/tools.py).
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.db import get_engine, session_scope  # noqa: E402
from app.jarvis import claude_brain, tools  # noqa: E402


def main(out: str) -> None:
    get_engine()
    with session_scope() as s:
        catalog = tools.elenca_serie(s)
        serie = {}
        for x in catalog["serie"]:
            per = {}
            for p in tools.PERIODS:
                q = tools.query_serie(s, x["id"], p)
                if q.get("punti"):
                    per[p] = q
            if per:
                serie[x["id"]] = per
        conv = tools.punteggio_convergenza(s)
        prev = tools.previsioni(s)
        data = {
            "registrato_il": date.today().isoformat(),
            "sistema": claude_brain.SYSTEM,
            "elenca_serie": catalog,
            "serie": serie,
            "regime": tools.regime_attuale(s),
            "scenari": {"": conv} | {
                sc["id"]: tools.punteggio_convergenza(s, sc["id"]) for sc in conv["scenari"]},
            "previsioni": prev,
            "previsione": {p["id"]: tools.previsione(s, p["id"]) for p in prev["previsioni"]},
            "track_record": tools.track_record(s),
        }
    Path(out).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"),
                                    default=str))
    print(f"recorded {len(serie)} series → {out}")


if __name__ == "__main__":
    main(sys.argv[1])
