"""
dashboard.py — Step 5. The daily scoreboard: how the funnel is converting and
whether each step is hitting its target (spec §4). Pure SQL over SQLite.

Exposes metrics() (a dict the web UI renders) and a standalone HTML renderer.

    python -m engine.dashboard            # write out/dashboard.html + print summary
"""

from __future__ import annotations

import datetime as dt
import sys

from . import db
from .common import OUT_DIR, get_logger, load_config

log = get_logger("dashboard")

# Targets from spec §4 (rates are fractions).
TARGETS = {
    "qualified_per_day": 25,
    "calls_per_day": 25,
    "conversation_rate": 0.20,   # reached a decision-maker / calls
    "send_audit_rate": 0.25,     # said "send me the audit" / conversations
    "close_rate": 0.15,          # sold / audits sent
}
CONVERSATION_STATUSES = ("NOT_INTERESTED", "SEND_AUDIT", "CALLBACK", "SOLD")


def _pct(a: int, b: int) -> float:
    return round(a / b, 3) if b else 0.0


def metrics() -> dict:
    cfg = load_config()
    price = float(cfg.get("offer", {}).get("price_aud", 0) or 0)
    rate = float(cfg.get("dashboard", {}).get("aud_to_pkr", 0) or 0)
    with db.connect() as conn:
        c = db.counts(conn)
        called = conn.execute("SELECT COUNT(DISTINCT lead_id) FROM outcomes").fetchone()[0]
        conversations = conn.execute(
            f"SELECT COUNT(DISTINCT lead_id) FROM outcomes WHERE status IN "
            f"({','.join('?'*len(CONVERSATION_STATUSES))})", CONVERSATION_STATUSES).fetchone()[0]
        audits_sent = conn.execute(
            "SELECT COUNT(DISTINCT lead_id) FROM outcomes WHERE status='SEND_AUDIT'").fetchone()[0]
        sold = conn.execute("SELECT COUNT(DISTINCT lead_id) FROM outcomes WHERE status='SOLD'").fetchone()[0]
        # 7-day trend of leads found
        trend = []
        for i in range(6, -1, -1):
            day = (dt.date.today() - dt.timedelta(days=i)).isoformat()
            n = conn.execute("SELECT COUNT(*) FROM leads WHERE substr(created_at,1,10)=?", (day,)).fetchone()[0]
            trend.append({"day": day[5:], "count": n})

    revenue_aud = sold * price
    funnel = {
        "found": c["leads"], "audited": c["audited"], "qualified": c["qualified"],
        "called": called, "conversations": conversations,
        "audits_sent": audits_sent, "sold": sold,
    }
    rates = {
        "conversation_rate": _pct(conversations, called),
        "send_audit_rate": _pct(audits_sent, conversations),
        "close_rate": _pct(sold, audits_sent),
    }
    # red flags vs targets
    flags = []
    if funnel["qualified"] < TARGETS["qualified_per_day"]:
        flags.append(("Qualified/day low", f"{funnel['qualified']} < {TARGETS['qualified_per_day']} — widen niches/cities or loosen a gate."))
    if funnel["called"] and rates["conversation_rate"] < TARGETS["conversation_rate"]:
        flags.append(("Conversation rate low", f"{rates['conversation_rate']:.0%} < {TARGETS['conversation_rate']:.0%} — try a different opener or call window."))
    if conversations and rates["send_audit_rate"] < TARGETS["send_audit_rate"]:
        flags.append(("Audit-ask rate low", f"{rates['send_audit_rate']:.0%} < {TARGETS['send_audit_rate']:.0%} — sharpen the one specific problem you lead with."))
    if audits_sent and rates["close_rate"] < TARGETS["close_rate"]:
        flags.append(("Close rate low", f"{rates['close_rate']:.0%} < {TARGETS['close_rate']:.0%} — revisit offer/price or niche fit."))
    return {
        "funnel": funnel, "rates": rates, "targets": TARGETS, "trend": trend, "flags": flags,
        "revenue_aud": revenue_aud, "revenue_pkr": revenue_aud * rate,
        "price_aud": price, "pkr_rate": rate,
    }


def render(m: dict, cfg: dict) -> str:
    """Standalone dashboard page (the web UI embeds the same data in its shell)."""
    from .webui import page, dashboard_body  # shared chrome
    return page("Dashboard", dashboard_body(m, cfg), cfg, active="dashboard")


def run() -> None:
    cfg = load_config()
    db.init_db()
    m = metrics()
    try:
        OUT_DIR.mkdir(exist_ok=True)
        (OUT_DIR / "dashboard.html").write_text(render(m, cfg), encoding="utf-8")
    except Exception as e:
        log.warning("could not write dashboard.html: %s", e)
    f = m["funnel"]
    log.info("Funnel: found %d · audited %d · qualified %d · called %d · conv %d · audits %d · sold %d",
             f["found"], f["audited"], f["qualified"], f["called"], f["conversations"],
             f["audits_sent"], f["sold"])
    log.info("Rates: conversation %.0f%% · send-audit %.0f%% · close %.0f%%",
             m["rates"]["conversation_rate"] * 100, m["rates"]["send_audit_rate"] * 100,
             m["rates"]["close_rate"] * 100)
    log.info("Revenue: A$%.0f  (₨%.0f)", m["revenue_aud"], m["revenue_pkr"])
    for title, msg in m["flags"]:
        log.warning("⚑ %s — %s", title, msg)


if __name__ == "__main__":
    sys.exit(run())
