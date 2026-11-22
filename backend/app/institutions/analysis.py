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


# ---- Deep dive: Buffett (value) and Dalio (regime) ----------------------------------------
def dcf(fcf: float, shares: float, cash: float, debt: float, growth: float, rate: float,
        terminal: float, years: int = 10) -> float | None:
    """Intrinsic value per share: free cash flow growing at ``growth`` and fading linearly
    to ``terminal`` over ``years``, discounted at ``rate``, plus a Gordon terminal value,
    plus net cash. None when the inputs cannot give a meaningful value."""
    if not fcf or fcf <= 0 or not shares or shares <= 0 or rate <= terminal:
        return None
    pv, cf = 0.0, fcf
    for y in range(1, years + 1):
        g = growth + (terminal - growth) * (y - 1) / max(years - 1, 1)
        cf *= 1 + g
        pv += cf / (1 + rate) ** y
    tv = cf * (1 + terminal) / (rate - terminal) / (1 + rate) ** years
    return (pv + tv + (cash or 0) - (debt or 0)) / shares


def buffett(info: dict, price: float | None, ten_year: float | None, rules) -> dict:
    """Quality checklist, earnings yield against the 10-year Treasury, DCF in three growth
    scenarios and the margin of safety. ``rules``: rqe ScreenerRules."""
    rate = max(rules.min_discount_rate, (ten_year or 0) + rules.equity_risk_premium)
    g_raw = info.get("crescita_utili")
    if g_raw is None:
        g_raw = info.get("crescita_ricavi")
    g = None if g_raw is None else float(np.clip(g_raw, 0.0, rules.max_growth))
    sc = {}
    if g is not None:
        for name, gg in (("prudente", g * 0.5), ("base", g), ("ottimista",
                                                             min(g * 1.5, rules.max_growth))):
            v = dcf(info.get("fcf"), info.get("azioni"), info.get("cassa"), info.get("debito"),
                    gg, rate, rules.terminal_growth, rules.years)
            sc[name] = {"crescita": round(gg, 4), "valore": None if v is None else round(v, 2),
                        "margine": None if v is None or not price or v <= 0
                        else round(1 - price / v, 4)}
    base = sc.get("base", {})
    ebitda, debt = info.get("ebitda"), info.get("debito")
    debt_ebitda = None if not ebitda or ebitda <= 0 or debt is None else debt / ebitda
    pe = info.get("pe")
    ey = None if not pe or pe <= 0 else 1 / pe
    checks = [
        ("ROE ≥ " + f"{rules.min_roe:.0%}", info.get("roe"),
         None if info.get("roe") is None else info["roe"] >= rules.min_roe),
        (f"Debito / EBITDA ≤ {rules.max_debt_ebitda:g}", debt_ebitda,
         None if debt_ebitda is None else debt_ebitda <= rules.max_debt_ebitda),
        ("Margine operativo ≥ 15% (potere sui prezzi)", info.get("margine_operativo"),
         None if info.get("margine_operativo") is None else info["margine_operativo"] >= 0.15),
        ("Flusso di cassa libero positivo", info.get("fcf"),
         None if info.get("fcf") is None else info["fcf"] > 0),
        ("Rendimento degli utili > Treasury 10 anni", ey,
         None if ey is None or ten_year is None else ey > ten_year),
        (f"Margine di sicurezza ≥ {rules.min_margin_of_safety:.0%} (scenario base)",
         base.get("margine"),
         None if base.get("margine") is None else base["margine"] >= rules.min_margin_of_safety),
    ]
    known = [c for c in checks if c[2] is not None]
    passed = sum(1 for c in known if c[2])
    if base.get("margine") is None:
        word = "Valore intrinseco non calcolabile con i dati disponibili."
    elif base["margine"] >= rules.min_margin_of_safety:
        word = "Sotto il valore intrinseco stimato con il margine di sicurezza richiesto."
    elif base["margine"] > 0:
        word = "Sotto il valore stimato, ma senza il margine di sicurezza richiesto."
    else:
        word = "Sopra il valore intrinseco stimato: per Buffett sarebbe caro."
    return {"tasso_sconto": round(rate, 4), "treasury_10a": ten_year,
            "rendimento_utili": None if ey is None else round(ey, 4),
            "debito_ebitda": None if debt_ebitda is None else round(debt_ebitda, 2),
            "scenari": sc, "controlli": [{"nome": n, "valore": None if v is None else
                                          round(float(v), 4), "ok": ok} for n, v, ok in checks],
            "superati": passed, "su": len(known), "sintesi": word}


def sector_by_regime(excess: pd.Series, regimes: pd.Series) -> dict:
    """Average excess return of a sector over the S&P 500 in the month after each month the
    regime ``q`` was the most likely (regime known at t, return of t+1): annualised mean,
    months and share of positive months."""
    r = excess.copy()
    r.index = r.index.to_period("M")
    reg = regimes.copy()
    reg.index = reg.index.to_period("M")
    nxt = reg.shift(1, freq="M")  # regime of the previous month, aligned to this month
    df = pd.DataFrame({"r": r, "q": nxt}).dropna()
    out = {}
    for q, g in df.groupby("q"):
        out[q] = {"eccesso_annuo": round(float(g["r"].mean() * 12), 4), "mesi": int(len(g)),
                  "quota_positivi": round(float((g["r"] > 0).mean()), 3)}
    return out
