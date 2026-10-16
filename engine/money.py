"""
money.py — The Money Loop. A self-learning expected-value engine.

Most lead tools rank by "fit". TDSOCH ranks by EXPECTED DOLLARS and learns from
your own outcomes. For every qualified lead it estimates:

    EV ($) = P(close | this kind of lead) × deal value

P(close) is built from the three funnel stages (reach a decision-maker → they
ask for the audit → they buy). Each stage starts from a sensible prior (the §4
targets) and is updated by your real logged outcomes using Beta–Binomial
shrinkage, hierarchically (a niche with no data = the global rate; with data it
moves toward its own). So the engine is honest when it's new and gets sharper
every time you log an outcome — a compounding money loop.

Pure Python, zero cost, fully explainable. No LLM.
"""

from __future__ import annotations

from . import db

# Funnel-stage priors (from the §4 targets) and how much they're "worth" in
# pseudo-observations before your real data takes over.
PRIOR = {"conv": 0.20, "ask": 0.25, "close": 0.15}
K_GLOBAL = 12      # prior strength for the global rates
K_NICHE = 8        # prior strength pulling a niche toward the global rate
UPSELL_MONTHS = 6          # expected life of a care-plan sale
UPSELL_TAKE_RATE = 0.30    # share of closes that take the monthly plan
CONVERSATION_STATUSES = ("NOT_INTERESTED", "SEND_AUDIT", "CALLBACK", "SOLD")


def _beta(successes: int, trials: int, prior_rate: float, k: float) -> float:
    """Posterior mean of a Beta–Binomial: shrinks toward prior_rate when data is thin."""
    return (successes + prior_rate * k) / (trials + k) if (trials + k) > 0 else prior_rate


def deal_value(cfg: dict) -> float:
    offer = cfg.get("offer", {})
    price = float(offer.get("price_aud", 0) or 0)
    monthly = float(offer.get("upsell_monthly_aud", 0) or 0)
    return price + monthly * UPSELL_MONTHS * UPSELL_TAKE_RATE


def _counts(conn, niche: str | None = None) -> dict:
    nf, args = ("AND l.niche = ?", [niche]) if niche else ("", [])
    def one(extra, a=()):
        return conn.execute(
            f"SELECT COUNT(DISTINCT o.lead_id) FROM outcomes o JOIN leads l ON l.id=o.lead_id "
            f"WHERE 1=1 {nf} {extra}", args + list(a)).fetchone()[0]
    called = one("")
    conv = one(f"AND o.status IN ({','.join('?'*len(CONVERSATION_STATUSES))})", CONVERSATION_STATUSES)
    sent = one("AND o.status='SEND_AUDIT'")
    sold = one("AND o.status='SOLD'")
    return {"called": called, "conversations": conv, "audits_sent": sent, "sold": sold}


def funnel_rates(conn) -> dict:
    c = _counts(conn)
    conv = _beta(c["conversations"], c["called"], PRIOR["conv"], K_GLOBAL)
    ask = _beta(c["audits_sent"], c["conversations"], PRIOR["ask"], K_GLOBAL)
    close = _beta(c["sold"], c["audits_sent"], PRIOR["close"], K_GLOBAL)
    return {"conv": conv, "ask": ask, "close": close, "counts": c,
            "p_call_to_sold": conv * ask * close}


def niche_rates(conn, niche: str, globals_: dict) -> dict:
    c = _counts(conn, niche)
    conv = _beta(c["conversations"], c["called"], globals_["conv"], K_NICHE)
    close = _beta(c["sold"], c["audits_sent"], globals_["close"], K_NICHE)
    # ask-rate is sparse per niche → use the global ask-rate
    p = conv * globals_["ask"] * close
    return {"conv": conv, "close": close, "p_call_to_sold": p, "counts": c}


def _score_factor(score: int | None) -> float:
    """Higher audit score (more pain + ability to pay) → a bit more likely to
    close. Maps 0–100 to 0.6–1.4, centred at 1.0 around score 50."""
    s = 50 if score is None else max(0, min(100, score))
    return 0.6 + 0.8 * (s / 100)


def lead_ev(niche: str | None, score: int | None, cfg: dict,
            globals_: dict, niche_cache: dict) -> float:
    if niche and niche not in niche_cache:
        niche_cache[niche] = niche_rates(_CONN.get(), niche, globals_) if _CONN.get() else None
    nr = niche_cache.get(niche) if niche else None
    p = (nr["p_call_to_sold"] if nr else globals_["p_call_to_sold"]) * _score_factor(score)
    return round(p * deal_value(cfg), 2)


# lightweight connection holder so lead_ev can lazily fetch niche rates
class _ConnHolder:
    def __init__(self):
        self._c = None
    def set(self, c):
        self._c = c
    def get(self):
        return self._c


_CONN = _ConnHolder()


def rank_by_ev(conn, cfg: dict, limit: int | None = None, qualified_only: bool = True) -> list[dict]:
    """Return active leads with an `ev` field, highest expected $ first."""
    _CONN.set(conn)
    g = funnel_rates(conn)
    cache: dict = {}
    where = "WHERE s.qualified=1" if qualified_only else "WHERE s.lead_id IS NOT NULL"
    rows = conn.execute(f"""
        SELECT l.*, s.score, s.tier, s.top_problem, s.reason
        FROM scores s JOIN leads l ON l.id=s.lead_id
        {where} AND l.status != 'suppressed'""").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # exclude already-sold from the open pipeline
        sold = conn.execute("SELECT 1 FROM outcomes WHERE lead_id=? AND status='SOLD' LIMIT 1",
                            (d["id"],)).fetchone()
        d["sold"] = bool(sold)
        d["ev"] = lead_ev(d.get("niche"), d.get("score"), cfg, g, cache)
        out.append(d)
    out.sort(key=lambda x: (x["sold"], -x["ev"]))   # open pipeline first, by EV
    return out[:limit] if limit else out


def pipeline(conn, cfg: dict) -> dict:
    g = funnel_rates(conn)
    leads = rank_by_ev(conn, cfg)
    open_leads = [l for l in leads if not l["sold"]]
    dv = deal_value(cfg)
    sold_n = g["counts"]["sold"]
    # best niches by learned EV-per-lead (with sample size)
    niches = [r[0] for r in conn.execute("SELECT DISTINCT niche FROM leads WHERE niche<>''")]
    segs = []
    for nm in niches:
        nr = niche_rates(conn, nm, g)
        segs.append({"niche": nm, "p": nr["p_call_to_sold"], "close": nr["close"],
                     "conv": nr["conv"], "ev_per_lead": round(nr["p_call_to_sold"] * dv, 2),
                     "called": nr["counts"]["called"], "sold": nr["counts"]["sold"]})
    segs.sort(key=lambda x: -x["ev_per_lead"])
    learned = g["counts"]["called"] >= 10 or g["counts"]["sold"] >= 1
    return {
        "pipeline_value": round(sum(l["ev"] for l in open_leads), 2),
        "open_count": len(open_leads),
        "realized": round(sold_n * dv, 2),
        "deal_value": dv,
        "rates": g, "segments": segs, "learned": learned,
        "top_leads": open_leads[:8],
        "next_action": next_best_action(conn, cfg, open_leads, segs),
    }


def next_best_action(conn, cfg: dict, open_leads: list[dict], segs: list[dict]) -> dict:
    import datetime as dt
    today = dt.date.today().isoformat()
    # 1) a callback due today/overdue
    cb = conn.execute(
        "SELECT o.lead_id, o.callback_at, l.name, l.root_domain, l.phone FROM outcomes o "
        "JOIN leads l ON l.id=o.lead_id WHERE o.status='CALLBACK' AND substr(o.callback_at,1,10)<=? "
        "ORDER BY o.callback_at LIMIT 1", (today,)).fetchone()
    if cb:
        return {"kind": "callback", "title": f"Call back {cb['name'] or cb['root_domain']}",
                "detail": f"due {cb['callback_at']}", "lead_id": cb["lead_id"], "phone": cb["phone"]}
    # 2) highest-EV lead you haven't called yet
    for l in open_leads:
        called = conn.execute("SELECT 1 FROM outcomes WHERE lead_id=? LIMIT 1", (l["id"],)).fetchone()
        if not called and l["phone"]:
            return {"kind": "call", "title": f"Call {l['name'] or l['root_domain']}",
                    "detail": f"${l['ev']:.0f} expected · {l.get('top_problem','') or ''}"[:70],
                    "lead_id": l["id"], "phone": l["phone"]}
    # 3) hunt the best segment
    if segs:
        b = segs[0]
        return {"kind": "hunt", "title": f"Hunt more {b['niche']}s",
                "detail": f"best expected value (${b['ev_per_lead']:.0f}/lead). Run the engine for more.",
                "lead_id": None, "phone": None}
    return {"kind": "run", "title": "Run the engine", "detail": "No active leads — go find some.",
            "lead_id": None, "phone": None}
