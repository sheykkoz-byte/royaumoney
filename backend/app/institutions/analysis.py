"""Pure functions: what changed between two 13F filings, how far the price has moved since,
whether the macro regime favours the sector, and a verdict with its reasons."""

import numpy as np
import pandas as pd

from app.institutions import config as C


def stocks(df: pd.DataFrame) -> pd.DataFrame:
    """Shares only (no options, no bonds), one row per CUSIP."""
    if df.empty:
        return df
    m = (df["put_call"].fillna("") == "") & (df["tipo"].fillna("SH") == "SH")
    return df[m].set_index("cusip")[["issuer", "classe", "valore", "quantita"]]


def changes(prev: pd.DataFrame, curr: pd.DataFrame,
            splits: dict[str, float] | None = None) -> pd.DataFrame:
    """Per CUSIP: shares before/after, change, kind (nuova, aumentata, ridotta, venduta,
    invariata), value now and weight in the portfolio."""
    p, c = stocks(prev), stocks(curr)
    idx = c.index.union(p.index)
    out = pd.DataFrame(index=idx)
    out["issuer"] = c["issuer"].combine_first(p["issuer"])
    out["prima"] = p["quantita"].reindex(idx).fillna(0)
    out["dopo"] = c["quantita"].reindex(idx).fillna(0)
    out["valore"] = c["valore"].reindex(idx).fillna(0)
    out["valore_prima"] = p["valore"].reindex(idx).fillna(0)
    total = float(c["valore"].sum()) or 1.0
    out["peso"] = out["valore"] / total
    # Implied price of each filing (value / shares) values the dollar change of the trade
    px = (out["valore"] / out["dopo"]).where(out["dopo"] > 0,
                                             out["valore_prima"] / out["prima"])
    out["variazione_quote"] = out["dopo"] - out["prima"]
    out["variazione_valore"] = out["variazione_quote"] * px.fillna(0)
    out["peso_variazione"] = out["variazione_valore"].abs() / total
    out["tipo"] = [_kind(a, b) for a, b in zip(out["prima"], out["dopo"], strict=False)]
    _code_changes(out)
    _splits(out, splits or {})
    return out


def _splits(out: pd.DataFrame, splits: dict[str, float]) -> None:
    """After a k-for-1 split (k from the split history, between the two quarter ends) a
    manager holds k times the shares: compare with the old shares × k so the split does
    not look like a purchase (or a reverse split like a sale)."""
    total = max(float(out["valore"].sum()), 1.0)
    for c, k in splits.items():
        if c not in out.index or not k or k == 1 or out.at[c, "prima"] <= 0:
            continue
        before = float(out.at[c, "prima"]) * k
        after = float(out.at[c, "dopo"])
        px = out.at[c, "valore"] / after if after else out.at[c, "valore_prima"] / before
        out.loc[c, "prima"] = before
        out.loc[c, "variazione_quote"] = after - before
        out.loc[c, "variazione_valore"] = (after - before) * px
        out.loc[c, "peso_variazione"] = abs(out.at[c, "variazione_valore"]) / total
        out.loc[c, "tipo"] = _kind(before, after)
        out.loc[c, "frazionamento"] = k


def _key(name: str) -> str:
    return "".join(ch for ch in str(name).upper() if ch.isalnum())[:5]


def _code_changes(out: pd.DataFrame, tolerance: float = 0.25) -> None:
    """A company that changes CUSIP (new holding company, re-domiciliation) looks like a
    full sale plus a new position. When a "nuova" and a "venduta" share the issuer's name
    and roughly the share count, the old row becomes "cambio di codice" and the new one is
    compared with the old shares (so a real trade on top still shows)."""
    sold = out[out["tipo"] == "venduta"]
    for c, r in out[out["tipo"] == "nuova"].iterrows():
        twin = sold[(sold["issuer"].map(_key) == _key(r["issuer"]))
                    & ((sold["prima"] / r["dopo"] - 1).abs() < tolerance)]
        if not len(twin):
            continue
        o = twin.index[0]
        before = float(out.at[o, "prima"])
        px = out.at[c, "valore"] / out.at[c, "dopo"]
        out.at[c, "prima"] = before
        out.at[c, "valore_prima"] = out.at[o, "valore_prima"]
        out.at[c, "variazione_quote"] = out.at[c, "dopo"] - before
        out.at[c, "variazione_valore"] = out.at[c, "variazione_quote"] * px
        out.at[c, "peso_variazione"] = abs(out.at[c, "variazione_valore"]) / \
            max(float(out["valore"].sum()), 1.0)
        out.at[c, "tipo"] = _kind(before, out.at[c, "dopo"])
        out.loc[o, "tipo"] = "cambio di codice"
        out.loc[o, ["variazione_quote", "variazione_valore", "peso_variazione"]] = 0.0
        sold = sold.drop(o)


def _kind(before: float, after: float) -> str:
    if before == 0 and after > 0:
        return "nuova"
    if after == 0 and before > 0:
        return "venduta"
    if before > 0 and after >= before * (1 + C.NEW_PCT):
        return "aumentata"
    if before > 0 and after <= before * (1 - C.NEW_PCT):
        return "ridotta"
    if after > before:
        return "aumentata poco"
    if after < before:
        return "ridotta poco"
    return "invariata"


def price_context(closes: pd.Series, period_end: pd.Timestamp) -> dict | None:
    """Estimated price paid (average close of the quarter ending at ``period_end``, with its
    range), the price at quarter end and the latest price."""
    closes = closes.dropna()
    start = period_end - pd.offsets.QuarterEnd(1)
    q = closes[(closes.index > start) & (closes.index <= period_end)]
    if q.empty or closes.empty:
        return None
    last = float(closes.iloc[-1])
    avg = float(q.mean())
    end_px = float(q.iloc[-1])
    return {"prezzo_medio_trimestre": round(avg, 2),
            "minimo_trimestre": round(float(q.min()), 2),
            "massimo_trimestre": round(float(q.max()), 2),
            "prezzo_fine_trimestre": round(end_px, 2),
            "prezzo_oggi": round(last, 2), "data_prezzo": closes.index[-1].date().isoformat(),
            "da_prezzo_medio": round(last / avg - 1, 4),
            "da_fine_trimestre": round(last / end_px - 1, 4)}


def regime_fit(sector: str | None, probs: dict[str, float],
               sectors: dict[str, list[str]]) -> float | None:
    """Probability that the regime is one that favours this sector (Σ P(q) over the
    quadrants whose list contains the sector)."""
    if not sector or not probs:
        return None
    return round(sum(p for q, p in probs.items() if sector in sectors.get(q, [])), 3)


def quality(info: dict) -> dict:
    """Buffett-style checks on what is available (None = no data)."""
    roe, de, fpe = info.get("roe"), info.get("debito_patrimonio"), info.get("pe_atteso")
    checks = {
        "roe": None if roe is None else roe >= C.MIN_ROE,
        "debito": None if de is None else de <= C.MAX_DEBT_EQUITY,
        "prezzo_utili": None if fpe is None else 0 < fpe <= C.MAX_FORWARD_PE,
    }
    known = [v for v in checks.values() if v is not None]
    return {"controlli": checks, "superati": sum(known), "su": len(known)}


def verdict(move: float | None, fit: float | None, q: dict | None,
            buyers: int, kind: str) -> dict:
    """Label and reasons in Italian. ``move``: price change from the estimated price paid."""
    reasons, score = [], 0
    if move is None:
        reasons.append("Prezzo non disponibile: impossibile dire se c'è ancora margine.")
    elif move > C.RAN_AWAY:
        score -= 2
        reasons.append(f"Il prezzo è già salito del {move:.0%} rispetto al prezzo medio "
                       "stimato del trimestre: gran parte del movimento è avvenuta.")
    elif move > C.NEAR_PAID:
        score -= 1
        reasons.append(f"Il prezzo è salito del {move:.0%} dal prezzo medio stimato: "
                       "si entrerebbe più cari di loro.")
    elif move < C.BELOW_PAID:
        reasons.append(f"Il prezzo è sceso del {-move:.0%} dal prezzo medio stimato: "
                       "loro sono in perdita, capire perché prima di seguirli.")
    elif move < 0:
        score += 2
        reasons.append(f"Il prezzo è del {-move:.0%} sotto il prezzo medio stimato del "
                       "trimestre: si entrerebbe a sconto rispetto a loro (ma è sceso: "
                       "verificare il motivo).")
    else:
        score += 2
        reasons.append(f"Il prezzo è vicino a quello pagato da loro ({move:+.0%}): "
                       "c'è ancora margine rispetto al loro ingresso.")
    if fit is None:
        reasons.append("Settore non disponibile: non so dire se il regime lo favorisce.")
    elif fit >= C.REGIME_GOOD:
        score += 1
        reasons.append(f"Il regime macro favorisce il settore (probabilità {fit:.0%}).")
    elif fit < C.REGIME_BAD:
        score -= 1
        reasons.append(f"Il regime macro non favorisce il settore (probabilità {fit:.0%}).")
    else:
        reasons.append(f"Il regime macro è neutro per il settore (probabilità {fit:.0%}).")
    if q and q["su"]:
        if q["superati"] == q["su"]:
            score += 1
        elif q["superati"] <= q["su"] / 2:
            score -= 1
        reasons.append(f"Qualità alla Buffett: {q['superati']} controlli superati su {q['su']}.")
    if buyers >= 2:
        score += 1
        reasons.append(f"Comprata da {buyers} gestori discrezionali nello stesso trimestre.")
    if kind == "nuova":
        reasons.append("Posizione nuova: è un'idea recente del gestore.")
    if score >= 3:
        label = "margine"
    elif move is not None and move > C.RAN_AWAY:
        label = "treno passato"
    elif fit is not None and fit < C.REGIME_BAD:
        label = "contro il regime"
    else:
        label = "da seguire"
    return {"giudizio": label, "punteggio": score, "motivi": reasons}


def days_late(period: str, filed: str, today: pd.Timestamp) -> dict:
    p, f = pd.Timestamp(period), pd.Timestamp(filed)
    return {"giorni_dalla_fine_trimestre": int((today - p).days),
            "giorni_di_ritardo_deposito": int((f - p).days)}


def safe(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else x


def latest_due_quarter(today: pd.Timestamp) -> pd.Timestamp:
    """The most recent quarter end whose 13F deadline (45 days) has passed."""
    q = (today - pd.Timedelta(days=45)) - pd.offsets.QuarterEnd(0)
    return q if q <= today - pd.Timedelta(days=45) else q - pd.offsets.QuarterEnd(1)
