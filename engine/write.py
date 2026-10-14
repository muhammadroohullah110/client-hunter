"""
write.py — the morning write step (Step 3). Turns qualified leads into
ready-to-use call openers, objection scripts, follow-up email drafts, and a
one-page HTML audit — using ONLY facts from the audit (never invented numbers).

By default this runs as a free, deterministic template engine (no API, no cost),
so the whole system works unattended. Openers/emails are built from each lead's
real top findings and niche. You (or Claude, in a session) can then polish any
individual opener — the data and structure are already in place.

    python -m engine.write                 # write drafts for the today queue (cap from config)
    python -m engine.write --limit 10
    python -m engine.write --dry-run        # print, write nothing
    python -m engine.write --lead 12        # just one lead

Respects do_not_email: for sites that publish a "no marketing" notice we still
write the call opener (calling a published business number is fine) but skip the
email draft.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys

from . import db
from .callsheet import NICHE_OBJECTIONS
from .common import OUT_DIR, get_logger, load_config

log = get_logger("write")

# Spoken opener templates keyed on the single biggest fixable problem.
# Each stays ≤ ~40 words and ends with a question. {me}/{biz} filled per lead.
OPENERS = {
    "no_https": "Hi, it's {me} — I was looking at {biz}'s website and noticed it's not on a secure connection, so some visitors get a 'Not secure' warning in their browser. Who looks after the website there?",
    "no_viewport": "Hi, it's {me} — I pulled up {biz}'s website on my phone and it doesn't fit the screen properly, which is where most people check these days. Who's the best person to talk to about the site?",
    "slow_lcp": "Hi, it's {me} — I had {biz}'s website open on my phone and it took about {lcp} seconds to load, which usually costs you calls. Who looks after the website there?",
    "low_psi": "Hi, it's {me} — I ran a quick speed check on {biz}'s website and it scored {psi} out of 100 on mobile, which usually means lost enquiries. Who handles the website?",
    "outdated_wp": "Hi, it's {me} — I had a look at {biz}'s website and it's running a WordPress version from a few years back, which tends to be slow and a bit exposed. Who looks after the site there?",
    "stale_copyright": "Hi, it's {me} — I was on {biz}'s website and the footer still says {year}, so it looks like it's been sitting a while. Who's looking after the website these days?",
    "_default": "Hi, it's {me} — I was looking at {biz}'s website and spotted a couple of quick things that are probably costing you enquiries. Who's the best person to talk to about the site?",
}

PROBLEM_ORDER = ["no_https", "no_viewport", "slow_lcp", "low_psi", "outdated_wp", "stale_copyright"]


def _pick_opener(findings: list[dict], audit: dict, me: str, biz: str) -> tuple[str, str]:
    """Return (opener_text, chosen_problem_type) from the lead's real findings."""
    ftypes = {f["type"] for f in findings}
    chosen = next((p for p in PROBLEM_ORDER if p in ftypes), "_default")
    tmpl = OPENERS.get(chosen, OPENERS["_default"])
    year = audit.get("footer_year") or ""
    lcp = audit.get("lcp") or ""
    psi = audit.get("psi_perf") if audit.get("psi_perf") is not None else ""
    text = tmpl.format(me=me or "there", biz=biz, year=year, lcp=lcp, psi=psi)
    return " ".join(text.split()), chosen


def _two_findings(findings: list[dict]) -> list[dict]:
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(findings, key=lambda f: order.get(f["severity"], 3))[:2]


def _email_draft(lead: dict, audit: dict, findings: list[dict], cfg: dict) -> tuple[str, str]:
    """Return (subject, body). Spam Act 2003: identifies sender + business,
    relates to the recipient's business, includes an unsubscribe line."""
    biz = lead["name"] or lead["root_domain"]
    me = cfg.get("my_name", "")
    business = cfg.get("business_name", "")
    phone = cfg.get("my_phone", "")
    email = cfg.get("my_email", "")
    price = cfg.get("offer", {}).get("price_aud", "")
    hours = cfg.get("offer", {}).get("delivery_hours", 48)
    pay = cfg.get("payment_link", "")

    two = _two_findings(findings)
    bullets = "\n".join(f"  {i}. {f['detail']}" for i, f in enumerate(two, 1))
    subject = f"Quick note about {biz}'s website"
    body = (
        f"Hi there,\n\n"
        f"I'm {me} from {business}. I had a quick look at {biz}'s website and "
        f"spotted a couple of things worth fixing:\n\n"
        f"{bullets}\n\n"
        f"I fix both for a fixed ${price} (done in {hours} hours, no lock-in). "
        f"Happy to send a free one-page audit first so you can see exactly what I mean.\n\n"
        f"{('Next step / payment: ' + pay) if pay else ''}\n"
        f"{me}\n{business} · {phone} · {email}\n\n"
        f"If you'd rather not hear from me, just reply with \"remove\" and I won't contact you again."
    )
    return subject, "\n".join(line for line in body.splitlines())


def _audit_html(lead: dict, audit: dict, findings: list[dict], cfg: dict) -> str:
    biz = html.escape(lead["name"] or lead["root_domain"])
    business = html.escape(str(cfg.get("business_name", "")))
    me = html.escape(str(cfg.get("my_name", "")))
    price = cfg.get("offer", {}).get("price_aud", "")
    hours = cfg.get("offer", {}).get("delivery_hours", 48)
    sev_color = {"high": "#d7263d", "medium": "#e8870b", "low": "#6b7280"}
    rows = "".join(
        f'<tr><td><span class="sev" style="background:{sev_color.get(f["severity"],"#6b7280")}">'
        f'{html.escape(f["severity"].upper())}</span></td><td>{html.escape(f["detail"])}</td></tr>'
        for f in findings)
    fixes = {
        "no_https": "Install a free SSL certificate and force HTTPS site-wide.",
        "no_viewport": "Add a mobile viewport and make the layout responsive.",
        "slow_lcp": "Compress images, enable caching + lazy-load to cut load time.",
        "low_psi": "Speed pass: image compression, caching, remove render-blocking scripts.",
        "outdated_wp": "Safely update WordPress core + plugins (full backup first).",
        "stale_copyright": "Refresh content, fix the footer year, general tidy-up.",
        "no_meta_description": "Write proper page titles + meta descriptions for Google.",
        "images_no_dims": "Add width/height to images to stop layout jumping.",
        "no_tel_link": "Add tap-to-call buttons so mobile visitors can ring in one tap.",
        "no_contact_form": "Add a simple contact/booking form to capture enquiries.",
    }
    todo = "".join(f"<li>{html.escape(fixes.get(f['type'], 'Fix: ' + f['type']))}</li>"
                   for f in _two_findings(findings))
    shot = ""
    if audit.get("screenshot_path"):
        shot = f'<img src="{html.escape(audit["screenshot_path"])}" alt="mobile screenshot" class="shot">'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Website Audit — {biz}</title>
<style>
 body{{font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:#1a1a1a;max-width:720px;margin:0 auto;padding:40px 24px}}
 h1{{font-size:24px;margin:0 0 4px}} .sub{{color:#666;margin-bottom:24px}}
 table{{width:100%;border-collapse:collapse;margin:16px 0}} td{{padding:8px;border-bottom:1px solid #eee;vertical-align:top}}
 .sev{{color:#fff;font-size:11px;padding:2px 8px;border-radius:4px}}
 .box{{background:#f4f7f5;border-left:4px solid #16a34a;padding:16px 20px;border-radius:8px;margin:20px 0}}
 .shot{{max-width:280px;border:1px solid #ddd;border-radius:10px;float:right;margin:0 0 16px 16px}}
 .cta{{background:#111;color:#fff;padding:14px 18px;border-radius:10px;margin-top:24px}}
 footer{{color:#888;font-size:12px;margin-top:30px;border-top:1px solid #eee;padding-top:12px}}
</style></head><body>
{shot}
<h1>Website audit — {biz}</h1>
<div class="sub">Prepared by {me}, {business} · {dt.date.today():%d %B %Y}</div>
<p>Here's what I found looking at your site, in plain words:</p>
<table>{rows}</table>
<div class="box"><b>What I'd fix in {hours} hours:</b><ul>{todo}</ul></div>
<div class="cta">Fixed price <b>${price}</b> · delivered in {hours} hours · no lock-in.
Reply to my email or call and I'll get started.</div>
<footer>{business} · {me}. This audit was prepared for {biz} based on a review of your public website.
If you'd prefer not to be contacted, just let me know and I'll remove you.</footer>
</body></html>"""


def write_one(conn, lead_id: int, cfg: dict, out_day, dry_run: bool) -> dict | None:
    lead = dict(conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())
    audit_row = db.audit_for(conn, lead_id)
    if not audit_row:
        return None
    audit = dict(audit_row)
    findings = json.loads(audit["findings_json"] or "[]")
    biz = lead["name"] or lead["root_domain"]
    me = cfg.get("my_name", "")

    opener, problem = _pick_opener(findings, audit, me, biz)
    objections = NICHE_OBJECTIONS.get(lead["niche"], [])
    price = cfg.get("offer", {}).get("price_aud", "")
    objections = [(o, a.replace("$[price]", f"${price}")) for o, a in objections]
    obj_text = "\n".join(f'"{o}" -> {a}' for o, a in objections)

    do_not_email = bool(audit["do_not_email"])
    if do_not_email:
        subject, body = "", "(skipped — site publishes a no-marketing notice; call only)"
    else:
        subject, body = _email_draft(lead, audit, findings, cfg)

    pdf_path = ""
    if not dry_run:
        out_day.mkdir(parents=True, exist_ok=True)
        pdf_path = str(out_day / f"{lead['root_domain']}.html")
        (out_day / f"{lead['root_domain']}.html").write_text(
            _audit_html(lead, audit, findings, cfg), encoding="utf-8")
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            "INSERT OR REPLACE INTO drafts (lead_id, opener, objections, email_subject, email_body, pdf_path, state, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (lead_id, opener, obj_text, subject, body, pdf_path, "draft", now))
    return {"lead": biz, "problem": problem, "opener": opener,
            "email": bool(subject), "pdf": pdf_path}


def run(limit: int | None = None, lead: int | None = None, dry_run: bool = False) -> int:
    cfg = load_config()
    cap = limit or cfg.get("daily_claude_leads_cap", 25)
    out_day = OUT_DIR / dt.date.today().isoformat()
    db.init_db()
    written = 0
    with db.connect() as conn:
        if lead:
            ids = [lead]
        else:
            ids = [r["id"] for r in db.today_queue(conn, cap)]
        log.info("Writing drafts for %d leads%s", len(ids), " (dry-run)" if dry_run else "")
        for lid in ids:
            res = write_one(conn, lid, cfg, out_day, dry_run)
            if not res:
                continue
            written += 1
            log.info("  %-28s [%s] email=%s", res["lead"], res["problem"], res["email"])
            if dry_run:
                log.info("      opener: %s", res["opener"])
    log.info("write complete: %d drafts%s → %s", written,
             " (dry-run: nothing written)" if dry_run else "", out_day)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Write openers + emails + audits for qualified leads.")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--lead", type=int, help="write just this lead id")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    run(limit=a.limit, lead=a.lead, dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
