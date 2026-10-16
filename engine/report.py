"""
report.py — SkyGen-level branded website audit report (+ PDF).

Runs a fresh deep audit of a lead's site, scores six categories (Speed, Mobile,
Security, SEO, Design, Conversion) into an overall grade, optionally adds an
AI expert verdict + prioritised fixes (if an API key is set), embeds a mobile
screenshot, and renders a branded report — HTML always, PDF when Playwright is
installed. Branding (colours, logo, tagline, WhatsApp/call) comes from config.

    python -m engine.report --lead 12          # report for a stored lead
    python -m engine.report --url example.com  # ad-hoc report for any URL
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import re
import sys
from pathlib import Path

from . import ai, audit as A, db
from .common import OUT_DIR, PoliteFetcher, get_logger, load_config

log = get_logger("report")

CTA_RE = re.compile(r"book\s*(now|online|appointment|a\s*consult)|get\s*(a\s*)?(quote|started)|"
                    r"call\s*(now|us|today)|request\s*(a\s*)?(quote|call|appointment)|"
                    r"free\s*consult|schedule\s*(now|online|a\s*visit)|enquire\s*now", re.I)
TRUST_RE = re.compile(r"testimonial|reviews?|google\s*rating|\d+\s*\+?\s*(years|yrs)\b|certified|"
                      r"accredited|award|guarantee|insured|licen[cs]ed|5[\s-]*star|★|⭐", re.I)

CAT_WEIGHTS = {"speed": .20, "mobile": .15, "security": .20, "seo": .15, "design": .15, "conversion": .15}


def _grade(score: float) -> str:
    return ("A+" if score >= 90 else "A" if score >= 85 else "B" if score >= 75
            else "C" if score >= 65 else "D" if score >= 50 else "F")


def deep_audit(url: str, cfg: dict, want_screenshot: bool = True, want_psi: bool | None = None) -> dict:
    fetcher = PoliteFetcher(rps=cfg.get("crawl", {}).get("requests_per_second_per_domain", 1),
                            timeout=cfg.get("crawl", {}).get("timeout_seconds", 15))
    if "://" not in url:
        url = "http://" + url
    status, final, h = fetcher.get(url)
    https_ok = (final or "").lower().startswith("https://")
    weight = len(h.encode()) if h else 0
    gen = A.GENERATOR_RE.search(h or "")
    gen_c = gen.group(1) if gen else ""
    wpv = A.WP_VER_RE.search(gen_c).group(1) if (gen_c and A.WP_VER_RE.search(gen_c)) else ""
    imgs = A.IMG_RE.findall(h or "")
    cta = len(CTA_RE.findall(h or ""))
    trust = len(set(m.group(0).lower() for m in TRUST_RE.finditer(h or "")))
    socials = A.find_socials(h or "")
    sig = {
        "http_status": status, "final_url": final or url, "https_ok": int(https_ok),
        "is_wordpress": int("wordpress" in gen_c.lower() or "wp-content" in (h or "")),
        "wp_version": wpv, "has_viewport": int(bool(A.VIEWPORT_RE.search(h or ""))),
        "footer_year": (int(A.YEAR_RE.search(h).group(1)) if A.YEAR_RE.search(h or "") else None),
        "page_weight": weight, "imgs_no_dims": sum(1 for t in imgs if not A.IMG_DIMS_RE.search(t)),
        "internal_links": A.internal_link_count(h or "", final or url),
        "has_title": int(bool(A.TITLE_RE.search(h or ""))),
        "has_meta_desc": int(bool(A.METADESC_RE.search(h or "") or A.OGDESC_RE.search(h or ""))),
        "has_tel": int(bool(A.TEL_RE.search(h or "") or A.TELNUM_RE.search(h or ""))),
        "has_form": int(bool(A.FORM_RE.search(h or ""))), "has_blog": int(bool(A.BLOG_RE.search(h or ""))),
        "has_social": int(any(socials.values())), "has_schema": int(bool(A.SCHEMA_RE.search(h or ""))),
        "has_booking": int(bool(A.BOOKING_RE.search(h or ""))), "has_ads_tag": int(bool(A.ADS_RE.search(h or ""))),
        "emails_found": ", ".join(A.extract_emails(h or "", url)), "do_not_email": 0,
        "cta_count": cta, "trust_signals": trust,
        "_has_og": bool(A.OG_RE.search(h or "")), "_has_favicon": bool(A.FAVICON_RE.search(h or "")),
        "_has_h1": bool(A.H1_RE.search(h or "")), "_styles": len(A.STYLESHEET_RE.findall(h or "")),
        "_dated_markup": bool(A.DATED_MARKUP_RE.search(h or "")),
    }
    if want_psi is None:
        want_psi = bool(cfg.get("crawl", {}).get("pagespeed", False))
    psi = A.pagespeed(final or url) if (want_psi and status and 200 <= status < 400) else \
        {"psi_perf": None, "lcp": None, "cls": None, "tbt": None}
    sig.update(psi)
    sig["findings_json"] = A.build_findings(sig, cfg)
    sig["scores"] = category_scores(sig)
    sig["screenshot_b64"] = _screenshot_b64(final or url) if (want_screenshot and status and 200 <= status < 400) else ""
    return sig


def category_scores(s: dict) -> dict:
    # Security
    sec = 100
    if not s["https_ok"]:
        sec -= 60
    if s["wp_version"]:
        try:
            if int(s["wp_version"].split(".")[0]) < 6:
                sec -= 25
        except ValueError:
            pass
    # Mobile
    mob = 100 if s["has_viewport"] else 35
    if s["_dated_markup"]:
        mob -= 15
    # Speed
    if s.get("psi_perf") is not None:
        speed = s["psi_perf"]
    else:
        kb = s["page_weight"] / 1024
        speed = max(25, min(85, 85 - max(0, (kb - 600) / 60)))  # rough proxy when no PSI
    # SEO
    seo = 100 - (25 if not s["has_title"] else 0) - (20 if not s["has_meta_desc"] else 0) \
        - (15 if not s["_has_h1"] else 0) - (10 if not s["has_schema"] else 0) - (10 if not s["_has_og"] else 0)
    # Design
    des = 100 - (40 if s["_dated_markup"] else 0) - (30 if s["_styles"] == 0 else 0) \
        - (10 if not s["_has_favicon"] else 0) - (10 if not s["has_social"] else 0)
    # Conversion
    con = 100 - (30 if not s["has_tel"] else 0) - (25 if not s["has_form"] else 0) \
        - (15 if s["cta_count"] == 0 else 0) + (5 if s["has_booking"] else 0) - (10 if s["trust_signals"] == 0 else 0)
    cats = {"speed": round(max(0, min(100, speed))), "mobile": max(0, min(100, mob)),
            "security": max(0, min(100, sec)), "seo": max(0, min(100, seo)),
            "design": max(0, min(100, des)), "conversion": max(0, min(100, con))}
    overall = round(sum(cats[k] * w for k, w in CAT_WEIGHTS.items()))
    cats["overall"] = overall
    cats["grade"] = _grade(overall)
    return cats


def _screenshot_b64(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            pg.goto(url, wait_until="networkidle", timeout=30000)
            png = pg.screenshot(full_page=False)
            b.close()
        return base64.b64encode(png).decode()
    except Exception as e:
        log.debug("screenshot failed: %s", e)
        return ""


def ai_insight(business: str, sig: dict, cfg: dict) -> dict | None:
    if not ai.ai_enabled(cfg):
        return None
    findings = "; ".join(f["detail"] for f in sig["findings_json"][:8]) or "none major"
    sc = sig["scores"]
    facts = (f"Business: {business}. Overall grade {sc['grade']} ({sc['overall']}/100). "
             f"Scores — speed {sc['speed']}, mobile {sc['mobile']}, security {sc['security']}, "
             f"seo {sc['seo']}, design {sc['design']}, conversion {sc['conversion']}. "
             f"HTTPS={bool(sig['https_ok'])}, mobile-viewport={bool(sig['has_viewport'])}, "
             f"CTAs={sig['cta_count']}, contact-form={bool(sig['has_form'])}, "
             f"phone-link={bool(sig['has_tel'])}, trust-signals={sig['trust_signals']}, "
             f"blog={bool(sig['has_blog'])}. Detected issues: {findings}.")
    system = ("You are a senior web consultant writing a short, honest audit for a local business "
              "owner (plain English, no jargon, Australian tone). Use ONLY the facts given — never "
              "invent numbers. Return strict JSON: {\"verdict\": \"one punchy sentence\", "
              "\"mistakes\": [{\"title\": \"...\", \"why\": \"why it costs them customers\"}], "
              "\"fixes\": [\"concrete fix\", ...]}. Max 3 mistakes, max 4 fixes.")
    return ai.complete_json(system, facts, cfg, max_tokens=700)


# ── Render ──────────────────────────────────────────────────────────────────────
def render_report_html(business: str, domain: str, sig: dict, insight: dict | None, cfg: dict) -> str:
    b = cfg.get("branding", {})
    brand = b.get("brand_color", "#2563EB")
    accent = b.get("accent_color", "#059669")
    biz_name = html.escape(str(cfg.get("business_name", "")))
    tagline = html.escape(str(b.get("tagline", "")))
    logo = b.get("logo_url", "")
    wa = re.sub(r"\D", "", str(b.get("whatsapp", "")))
    phone = re.sub(r"[^\d+]", "", str(cfg.get("my_phone", "")))
    sc = sig["scores"]
    grade_color = accent if sc["overall"] >= 75 else ("#f59e0b" if sc["overall"] >= 55 else "#dc2626")

    def bar(label, val):
        c = accent if val >= 75 else ("#f59e0b" if val >= 50 else "#dc2626")
        return (f'<div class="cat"><div class="cl"><span>{label}</span><b>{val}</b></div>'
                f'<div class="ct"><div class="cf" style="width:{val}%;background:{c}"></div></div></div>')
    cats = "".join(bar(l, sc[k]) for k, l in [("speed", "Speed"), ("mobile", "Mobile"),
            ("security", "Security"), ("seo", "SEO / Google"), ("design", "Design"), ("conversion", "Conversion")])

    sev_color = {"high": "#dc2626", "medium": "#d97706", "low": "#6b7280"}
    findings = "".join(
        f'<tr><td><span class="sev" style="background:{sev_color.get(f["severity"],"#6b7280")}">'
        f'{html.escape(f["severity"].upper())}</span></td><td>{html.escape(f["detail"])}</td></tr>'
        for f in sorted(sig["findings_json"], key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["severity"], 3)))

    if insight:
        mistakes = "".join(f'<li><b>{html.escape(m.get("title",""))}</b> — {html.escape(m.get("why",""))}</li>'
                           for m in (insight.get("mistakes") or [])[:3])
        fixes = "".join(f"<li>{html.escape(x)}</li>" for x in (insight.get("fixes") or [])[:4])
        ai_block = (f'<div class="ai"><div class="verdict">“{html.escape(insight.get("verdict",""))}”</div>'
                    f'<h3>Biggest mistakes costing you customers</h3><ul>{mistakes}</ul>'
                    f'<h3>What we\'d fix first</h3><ul>{fixes}</ul></div>')
    else:
        ai_block = ('<div class="ai muted">Add a free AI key in Settings to include an expert '
                    'written verdict and prioritised fixes here.</div>')

    shot = (f'<img class="shot" src="data:image/png;base64,{sig["screenshot_b64"]}" alt="site screenshot">'
            if sig.get("screenshot_b64") else "")
    logo_html = f'<img src="{html.escape(logo)}" alt="logo" class="logo">' if logo else f'<span class="wm">{biz_name}</span>'
    cta_btns = ""
    if phone:
        cta_btns += f'<a class="cta call" href="tel:{html.escape(phone)}">Call {html.escape(cfg.get("my_phone",""))}</a>'
    if wa:
        cta_btns += f'<a class="cta wa" href="https://wa.me/{wa}">WhatsApp us</a>'

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Website Audit — {html.escape(business)}</title>
<style>
@page{{size:A4;margin:14mm}}
*{{box-sizing:border-box}} body{{font:14px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#15202b;margin:0}}
.bar{{height:7px;background:linear-gradient(90deg,{brand},{accent})}}
.wrap{{max-width:800px;margin:0 auto;padding:26px 30px}}
header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}}
.logo{{height:38px}} .wm{{font-weight:800;font-size:19px;color:{brand}}}
h1{{font-size:25px;margin:14px 0 2px}} .sub{{color:#64748b;margin-bottom:18px}}
.hero{{display:flex;gap:22px;align-items:center;background:#f6f9fc;border:1px solid #e6eef7;border-radius:14px;padding:20px;margin-bottom:20px}}
.dial{{width:112px;height:112px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;
 color:#fff;background:{grade_color};flex-shrink:0}} .dial .g{{font-size:34px;font-weight:800;line-height:1}} .dial .n{{font-size:12px;opacity:.9}}
.cats{{flex:1}} .cat{{margin:7px 0}} .cl{{display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px}}
.ct{{background:#e6eef7;border-radius:6px;height:9px;overflow:hidden}} .cf{{height:100%;border-radius:6px}}
h2{{font-size:16px;margin:22px 0 10px;border-left:4px solid {brand};padding-left:10px}}
.ai{{background:#fbfdff;border:1px solid #e6eef7;border-radius:12px;padding:18px}}
.verdict{{font-size:18px;font-weight:700;color:{brand};margin-bottom:10px}}
.ai h3{{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#64748b;margin:14px 0 6px}}
.ai.muted{{color:#64748b}} ul{{margin:0;padding-left:18px}} li{{margin:5px 0}}
.shot{{width:100%;border:1px solid #e2e8f0;border-radius:10px;margin:8px 0}}
table{{width:100%;border-collapse:collapse}} td{{padding:7px 8px;border-bottom:1px solid #eef2f6;vertical-align:top}}
.sev{{color:#fff;font-size:10px;padding:2px 7px;border-radius:4px}}
.ctas{{display:flex;gap:12px;margin:18px 0}} .cta{{padding:12px 20px;border-radius:9px;color:#fff;text-decoration:none;font-weight:700}}
.cta.call{{background:{brand}}} .cta.wa{{background:{accent}}}
footer{{color:#94a3b8;font-size:11px;border-top:1px solid #eef2f6;margin-top:22px;padding-top:12px}}
</style></head><body>
<div class="bar"></div>
<div class="wrap">
 <header>{logo_html}<span style="color:#94a3b8;font-size:12px">{dt.date.today():%d %B %Y}</span></header>
 <h1>Website audit — {html.escape(business)}</h1>
 <div class="sub">{html.escape(domain)}{(' · ' + tagline) if tagline else ''}</div>
 <div class="hero">
   <div class="dial"><div class="g">{sc['grade']}</div><div class="n">{sc['overall']}/100</div></div>
   <div class="cats">{cats}</div>
 </div>
 <h2>The expert take</h2>
 {ai_block}
 {('<h2>What your site looks like</h2>' + shot) if shot else ''}
 <h2>Everything we found</h2>
 <table>{findings or '<tr><td>No major issues found.</td></tr>'}</table>
 <div class="ctas">{cta_btns}</div>
 <footer>Prepared by {biz_name}. Based on a review of your public website on {dt.date.today():%d %b %Y}.
   This is a free summary — there's more we can walk you through.</footer>
</div></body></html>"""


def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto(html_path.as_uri(), wait_until="networkidle", timeout=30000)
            pg.pdf(path=str(pdf_path), format="A4", print_background=True)
            b.close()
        return True
    except Exception as e:
        log.warning("PDF render needs Playwright (pip install playwright && playwright install chromium): %s", e)
        return False


def generate(lead: dict, cfg: dict) -> dict:
    business = lead.get("name") or lead.get("root_domain")
    domain = lead.get("root_domain") or lead.get("website", "")
    url = lead.get("website") or domain
    log.info("deep audit: %s", domain)
    sig = deep_audit(url, cfg)
    insight = ai_insight(business, sig, cfg)
    html_doc = render_report_html(business, domain, sig, insight, cfg)
    out = OUT_DIR / dt.date.today().isoformat() / "reports"
    out.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", domain) or "report"
    html_path = out / f"{safe}.html"
    html_path.write_text(html_doc, encoding="utf-8")
    pdf_path = out / f"{safe}.pdf"
    pdf_ok = html_to_pdf(html_path, pdf_path)
    log.info("report: grade %s (%d/100) → %s%s", sig["scores"]["grade"], sig["scores"]["overall"],
             html_path.name, " + PDF" if pdf_ok else " (HTML only)")
    return {"grade": sig["scores"]["grade"], "overall": sig["scores"]["overall"],
            "html_path": str(html_path), "pdf_path": str(pdf_path) if pdf_ok else "",
            "scores": sig["scores"], "ai": bool(insight)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a branded website audit report (+PDF).")
    ap.add_argument("--lead", type=int)
    ap.add_argument("--url", help="ad-hoc report for any URL")
    a = ap.parse_args()
    cfg = load_config()
    db.init_db()
    if a.url:
        lead = {"name": a.url, "root_domain": a.url, "website": a.url}
    elif a.lead:
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM leads WHERE id=?", (a.lead,)).fetchone()
        if not row:
            sys.exit("lead not found")
        lead = dict(row)
    else:
        sys.exit("pass --lead <id> or --url <url>")
    res = generate(lead, cfg)
    print(res["html_path"], res.get("pdf_path", ""))


if __name__ == "__main__":
    sys.exit(main())
