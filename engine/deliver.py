"""
deliver.py — Step 7. The fix playbook for a SOLD lead (semi-automated).

Generates a step-by-step, audit-specific fix checklist (backup first, then the
exact fixes this site needs), and — once you've applied the fixes and re-run the
audit — a before/after report plus a draft upsell email for the monthly care
plan.

IMPORTANT: this never logs into a client site or changes anything. It only
prepares checklists and drafts. You apply the fixes, with the client's go-ahead.

    python -m engine.deliver --lead 12                 # fix playbook for lead 12
    python -m engine.deliver --lead 12 --reaudit       # re-audit + before/after report
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys

from . import audit as audit_mod
from . import db
from .common import OUT_DIR, PoliteFetcher, get_logger, load_config

log = get_logger("deliver")

# Audit finding → concrete fix steps (WordPress-first, since most SMB sites are WP).
FIX_STEPS = {
    "no_https": ["Install a free SSL certificate (Let's Encrypt via host / cPanel AutoSSL).",
                 "Force HTTPS: add a 301 redirect from http→https.",
                 "Update site URL to https in settings; fix mixed-content warnings."],
    "no_viewport": ["Add <meta name=viewport> to the theme header.",
                    "Switch to / fix a responsive theme; test on a real phone."],
    "slow_lcp": ["Install a caching plugin (WP Super Cache / LiteSpeed).",
                 "Compress + convert images to WebP (ShortPixel / Imagify free tier).",
                 "Enable lazy-load; defer render-blocking JS/CSS."],
    "low_psi": ["Run the speed pass: caching, image compression, lazy-load.",
                "Remove unused plugins and heavy sliders.",
                "Minify CSS/JS; preload the hero image."],
    "outdated_wp": ["Take a FULL backup first (UpdraftPlus or host snapshot).",
                    "Update WordPress core + plugins on a staging copy if available.",
                    "Test the site, then push updates live."],
    "stale_copyright": ["Update the footer year + refresh key copy.",
                        "Check for dead links and outdated info."],
    "no_meta_description": ["Install an SEO plugin (Yoast / RankMath).",
                            "Write unique titles + meta descriptions for key pages."],
    "images_no_dims": ["Add width/height attributes (or aspect-ratio) to images."],
    "no_tel_link": ["Make the phone number a tap-to-call tel: link, header + footer."],
    "no_contact_form": ["Add a simple contact/booking form (WPForms / Fluent Forms)."],
}

ALWAYS_FIRST = ["Confirm written go-ahead + admin/hosting access from the client.",
                "Take a FULL backup (files + database) before touching anything.",
                "Note the current PageSpeed score + load time (the 'before')."]


def playbook_html(lead: dict, findings: list[dict], cfg: dict) -> str:
    biz = html.escape(lead["name"] or lead["root_domain"])
    steps_html = ""
    for f in sorted(findings, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["severity"], 3)):
        fixes = FIX_STEPS.get(f["type"])
        if not fixes:
            continue
        lis = "".join(f"<li>{html.escape(s)}</li>" for s in fixes)
        steps_html += (f'<div class="blk"><h3>{html.escape(f["detail"])}</h3>'
                       f'<ul>{lis}</ul></div>')
    first = "".join(f"<li>{html.escape(s)}</li>" for s in ALWAYS_FIRST)
    upsell = cfg.get("offer", {}).get("upsell_monthly_aud", "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fix playbook — {biz}</title>
<style>body{{font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;max-width:740px;margin:0 auto;padding:40px 24px;color:#1a1a1a}}
h1{{font-size:24px}} h3{{font-size:15px;margin:0 0 6px}} .blk{{background:#f6f8f7;border-radius:8px;padding:14px 18px;margin:12px 0}}
.first{{background:#fff7e6;border-left:4px solid #e8870b;padding:14px 18px;border-radius:8px}}
.care{{background:#111;color:#fff;padding:14px 18px;border-radius:10px;margin-top:20px}}</style></head><body>
<h1>Fix playbook — {biz}</h1>
<div class="first"><b>Before you start:</b><ol>{first}</ol></div>
<h2>Fixes (in order)</h2>
{steps_html or '<p>No automated fixes mapped — review the audit.</p>'}
<div class="care">After delivery, offer the care plan: updates, backups, speed &amp; security monitoring
for <b>${upsell}/month</b>. Draft email saved alongside this file.</div>
</body></html>"""


def upsell_email(lead: dict, cfg: dict) -> str:
    me = cfg.get("my_name", ""); business = cfg.get("business_name", "")
    monthly = cfg.get("offer", {}).get("upsell_monthly_aud", "")
    biz = lead["name"] or lead["root_domain"]
    return (f"Subject: Keeping {biz}'s site fast & safe\n\n"
            f"Hi,\n\nNow that the fixes are live, the main thing is keeping it that way — "
            f"WordPress and plugins need regular updates, backups, and a speed/security eye.\n\n"
            f"I can look after all of that for ${monthly}/month, cancel anytime. Want me to set it up?\n\n"
            f"{me}\n{business}")


def playbook(lead_id: int) -> None:
    cfg = load_config()
    with db.connect() as conn:
        lead = dict(conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())
        a = db.audit_for(conn, lead_id)
    findings = json.loads(a["findings_json"]) if a and a["findings_json"] else []
    out = OUT_DIR / dt.date.today().isoformat() / "deliver"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{lead['root_domain']}-playbook.html").write_text(playbook_html(lead, findings, cfg), encoding="utf-8")
    (out / f"{lead['root_domain']}-upsell.txt").write_text(upsell_email(lead, cfg), encoding="utf-8")
    log.info("playbook → %s", out / f"{lead['root_domain']}-playbook.html")


def reaudit(lead_id: int) -> None:
    cfg = load_config()
    with db.connect() as conn:
        lead = dict(conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())
        before = db.audit_for(conn, lead_id)
        before_findings = json.loads(before["findings_json"]) if before and before["findings_json"] else []
    fetcher = PoliteFetcher(rps=cfg.get("crawl", {}).get("requests_per_second_per_domain", 1),
                            timeout=cfg.get("crawl", {}).get("timeout_seconds", 15))
    after = audit_mod.audit_one(fetcher, lead, cfg, do_screenshot=False, do_psi=True)
    after_findings = after["findings_json"]
    b = {f["type"] for f in before_findings}
    a = {f["type"] for f in after_findings}
    fixed = sorted(b - a)
    remaining = sorted(a)
    log.info("── BEFORE/AFTER for %s ──", lead["root_domain"])
    log.info("  fixed: %s", ", ".join(fixed) or "—")
    log.info("  remaining: %s", ", ".join(remaining) or "none 🎉")
    out = OUT_DIR / dt.date.today().isoformat() / "deliver"
    out.mkdir(parents=True, exist_ok=True)
    report = (f"Before/after — {lead['name'] or lead['root_domain']}\n"
              f"{'='*50}\nFixed: {', '.join(fixed) or '-'}\nRemaining: {', '.join(remaining) or 'none'}\n")
    (out / f"{lead['root_domain']}-before-after.txt").write_text(report, encoding="utf-8")
    log.info("report → %s", out / f"{lead['root_domain']}-before-after.txt")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fix playbook + before/after for a SOLD lead.")
    ap.add_argument("--lead", type=int, required=True)
    ap.add_argument("--reaudit", action="store_true", help="re-audit and produce before/after")
    a = ap.parse_args()
    db.init_db()
    if a.reaudit:
        reaudit(a.lead)
    else:
        playbook(a.lead)


if __name__ == "__main__":
    sys.exit(main())
