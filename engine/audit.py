"""
audit.py — free technical audit of each lead's website. No LLM, no paid APIs.

For each new lead: fetch homepage (+ up to a couple of contact/about pages),
record HTTPS / viewport / WordPress / title / meta / tel / form / page weight /
images-without-dimensions / internal-link count, detect booking widgets and ad
pixels (budget signals), harvest published business emails and social handles
(technique adapted from google-maps-scraper-kit), optionally pull PageSpeed
Insights mobile metrics, optionally screenshot via Playwright, and derive a
severity-tagged findings list. Everything saved to SQLite.

    python -m engine.audit               # audit every lead with status 'new'
    python -m engine.audit --dry-run     # audit + print, write nothing
    python -m engine.audit --limit 20 --no-screenshot
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from . import db
from .common import (AUDIT_DIR, PoliteFetcher, get_logger, load_config, load_env,
                     root_domain, user_agent)

log = get_logger("audit")

# ── Regex toolkit (adapted from google-maps-scraper-kit, extended) ───────────
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAILTO_RE = re.compile(r"mailto:([^\"'>\s?]+)", re.I)
HREF_RE = re.compile(r"<a\s[^>]*?href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
VIEWPORT_RE = re.compile(r'<meta[^>]+name=["\']viewport["\']', re.I)
METADESC_RE = re.compile(r'<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']+)', re.I)
GENERATOR_RE = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]*content=["\']([^"\']+)', re.I)
# WordPress CORE version ONLY — from the generator string ("WordPress 5.8.1").
# NEVER from `?ver=` on assets: that's a plugin/theme version (e.g. ver=7.1.3),
# which is NOT a WP core version and caused false "outdated" flags.
WP_VER_RE = re.compile(r"wordpress[\s/]+v?([0-9]+(?:\.[0-9]+){0,2})", re.I)
TEL_RE = re.compile(r'href=["\'](?:tel|callto):', re.I)
TELNUM_RE = re.compile(r"\b(?:0[2-8]|13|1300|1800)(?:[\s)(.-]?\d){6,9}\b")  # visible AU number
FORM_RE = re.compile(r"<form[\s>]|wpforms|gravity[-_]?form|fluentform|typeform\.com|"
                     r"jotform|hsforms|wpcf7|contact-form-7|calendly\.com|<iframe[^>]+form", re.I)
IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
IMG_DIMS_RE = re.compile(r"\b(?:width|height)\s*=|aspect-ratio|loading\s*=\s*[\"']?lazy", re.I)
SCHEMA_RE = re.compile(r'application/ld\+json|itemscope|itemtype=', re.I)
YEAR_RE = re.compile(r"(?:©|&copy;|copyright)[^0-9]{0,20}(20\d{2})", re.I)
# ── Design-issue signals (what a visitor actually sees) ───────────────────────
OGDESC_RE = re.compile(r'property=["\']og:description["\']', re.I)
OG_RE = re.compile(r'property=["\']og:(?:title|image)["\']', re.I)
FAVICON_RE = re.compile(r'rel=["\'][^"\']*icon[^"\']*["\']', re.I)
H1_RE = re.compile(r"<h1[\s>]", re.I)
STYLESHEET_RE = re.compile(r"<link[^>]+stylesheet|<style[\s>]", re.I)
DATED_MARKUP_RE = re.compile(r"<(?:font|center|marquee|frameset|blink)\b|\bbgcolor=|"
                             r"<table[^>]+\bwidth=[\"']?\d", re.I)

SOCIAL_RE = {
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)", re.I),
    "facebook": re.compile(r"https?://(?:www\.|m\.|web\.)?facebook\.com/([A-Za-z0-9_.\-]+)", re.I),
    "linkedin": re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|in|school)/([A-Za-z0-9_.\-%]+)", re.I),
}
_SKIP_HANDLE = {"", "home", "pages", "people", "help", "about", "policies", "policy", "legal",
                "tos", "privacy", "settings", "sharer", "tr", "profile.php", "plugins", "dialog",
                "intent", "login", "share.php", "permalink.php", "p", "reel", "reels", "explore",
                "stories", "tv", "watch", "events", "groups", "marketplace", "sharer.php"}
_JUNK_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
_JUNK_DOMAIN = ("example", "sentry", "wixpress", "wix.com", "godaddy", "squarespace",
                "wordpress", "domain.com", "email.com", "yourdomain", "schema.org", "w3.org")
_JUNK_LOCAL = {"name", "email", "user", "you", "someone"}

BOOKING_RE = re.compile(r"cliniko|hotdoc|healthengine|calendly|acuity|setmore|fresha|dentalhub|"
                        r"book\s*(?:now|online|appointment)|online\s*booking", re.I)
ADS_RE = re.compile(r"gtag\(|googletagmanager\.com|AW-\d|google_conversion|fbq\(|facebook\.net/.+?/fbevents", re.I)
BLOG_RE = re.compile(r"/blog|/news|/articles|>\s*blog\s*<|>\s*news\s*<", re.I)
NO_MARKETING_RE = re.compile(r"no\s+unsolicited|no\s+marketing|do\s+not\s+(?:email|contact)|"
                             r"not\s+accept.{0,20}marketing", re.I)


def _host(url: str) -> str:
    if "://" not in url:
        url = "http://" + url
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def extract_emails(html: str, site_host: str) -> list[str]:
    site = _host(site_host or "")
    found: list[str] = []
    for e in MAILTO_RE.findall(html or "") + EMAIL_RE.findall(html or ""):
        e = urllib.parse.unquote(e).strip().lower()
        local, _, dom = e.rpartition("@")
        if (not EMAIL_RE.fullmatch(e) or e.endswith(_JUNK_EXT) or local in _JUNK_LOCAL
                or any(j in dom for j in _JUNK_DOMAIN) or e in found):
            continue
        found.append(e)
    on_site = lambda e: site and (e.endswith("@" + site) or e.endswith("." + site))
    return sorted(found, key=lambda e: not on_site(e))[:3]


def find_socials(html: str) -> dict[str, str]:
    out = {"instagram": "", "facebook": "", "linkedin": ""}
    for plat, rx in SOCIAL_RE.items():
        for m in rx.finditer(html or ""):
            h = m.group(1).lower()
            if h in _SKIP_HANDLE:
                continue
            if plat == "facebook" and (h.isdigit() or len(h) < 3):
                continue
            out[plat] = m.group(0).rstrip("\"'/").replace("\\", "")
            break
    return out


def contact_links(html: str, base_url: str, limit: int) -> list[str]:
    if "://" not in base_url:
        base_url = "http://" + base_url
    host, out = _host(base_url), []
    for href, text in HREF_RE.findall(html or ""):
        if not re.search(r"contact|about", href + " " + text, re.I):
            continue
        url = urllib.parse.urldefrag(urllib.parse.urljoin(base_url, href.strip()))[0]
        if url.startswith(("http://", "https://")) and _host(url) == host and url not in out:
            out.append(url)
    for path in ("/contact", "/contact-us", "/about"):
        url = urllib.parse.urljoin(base_url, path)
        if len(out) < limit and url not in out:
            out.append(url)
    return out[:limit]


def internal_link_count(html: str, base_url: str) -> int:
    host, paths = _host(base_url), set()
    for href, _ in HREF_RE.findall(html or ""):
        url = urllib.parse.urljoin(base_url, href.strip())
        if url.startswith(("http://", "https://")) and _host(url) == host:
            path = urllib.parse.urlparse(url).path.rstrip("/").lower()
            if path and path not in ("", "/"):
                paths.add(path)
    return len(paths)


# ── PageSpeed Insights (free; key optional, only raises quota) ───────────────
def pagespeed(url: str) -> dict:
    key = os.environ.get("PSI_KEY", "").strip()
    params = {"url": url, "strategy": "mobile", "category": "performance"}
    if key:
        params["key"] = key
    api = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(api, headers={"User-Agent": user_agent()})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        lh = data.get("lighthouseResult", {})
        audits = lh.get("audits", {})
        perf = lh.get("categories", {}).get("performance", {}).get("score")
        return {
            "psi_perf": round(perf * 100) if perf is not None else None,
            "lcp": _num(audits.get("largest-contentful-paint", {}).get("numericValue"), 1000),
            "cls": audits.get("cumulative-layout-shift", {}).get("numericValue"),
            "tbt": _num(audits.get("total-blocking-time", {}).get("numericValue"), 1),
        }
    except Exception as e:
        log.debug("PSI failed for %s: %s", url, e)
        return {"psi_perf": None, "lcp": None, "cls": None, "tbt": None}


def _num(v, div):
    return round(v / div, 2) if isinstance(v, (int, float)) else None


# ── Screenshot (optional Playwright) ──────────────────────────────────────────
def screenshot(url: str, rd: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""
    path = AUDIT_DIR / rd / "mobile.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.screenshot(path=str(path))
            b.close()
        return str(path)
    except Exception as e:
        log.debug("screenshot failed %s: %s", url, e)
        return ""


# ── Findings ──────────────────────────────────────────────────────────────────
def build_findings(a: dict, cfg: dict) -> list[dict]:
    q = cfg.get("qualify", {})
    psi_fail = q.get("psi_fail_threshold", 50)
    lcp_fail = q.get("lcp_fail_seconds", 4.0)
    stale_years = q.get("copyright_stale_years", 2)
    this_year = dt.date.today().year
    f: list[dict] = []

    def add(t, sev, detail):
        f.append({"type": t, "severity": sev, "detail": detail})

    if not a["https_ok"]:
        add("no_https", "high", "Site not served over HTTPS — browsers show 'Not secure'")
    if not a["has_viewport"]:
        add("no_viewport", "high", "No mobile viewport meta — page not mobile-friendly")
    if a["psi_perf"] is not None and a["psi_perf"] < psi_fail:
        add("low_psi", "high", f"PageSpeed mobile {a['psi_perf']}/100 (below {psi_fail})")
    if a["lcp"] is not None and a["lcp"] > lcp_fail:
        add("slow_lcp", "high", f"Largest Contentful Paint {a['lcp']}s (slow; >{lcp_fail}s)")
    if not a["has_title"]:
        add("no_title", "high", "Missing <title> tag")
    if not a["has_meta_desc"]:
        add("no_meta_description", "medium", "No meta description — weaker Google snippet")
    if a["footer_year"] and a["footer_year"] <= this_year - stale_years:
        add("stale_copyright", "medium", f"Footer copyright says {a['footer_year']} (looks neglected)")
    # outdated_wp ONLY when the CORE version is genuinely old (major < 6, i.e.
    # pre-2022). A modern WP 6.x site is NOT flagged — this was the false-positive bug.
    if a["is_wordpress"] and a["wp_version"]:
        try:
            major = int(a["wp_version"].split(".")[0])
        except ValueError:
            major = 99
        if major < 6:
            add("outdated_wp", "medium",
                f"WordPress {a['wp_version']} is several years old (security + speed risk)")
    if a["imgs_no_dims"] and a["imgs_no_dims"] >= 8:
        add("images_no_dims", "low", f"{a['imgs_no_dims']} images without dimensions (can cause layout shift)")
    if not a["has_tel"]:
        add("no_tel_link", "low", "No click-to-call link or visible number on the homepage")
    if not a["has_form"]:
        add("no_contact_form", "low", "No contact/booking form detected on the homepage")

    # ── Design issues (what a visitor actually sees) ──────────────────────────
    if a.get("_dated_markup"):
        add("dated_design", "high", "Dated page code (table layouts / old tags) — looks out-of-date to visitors")
    if a.get("_styles", 1) == 0:
        add("unstyled", "high", "Almost no styling detected — the page looks unformatted")
    if not a.get("_has_og", True):
        add("no_social_preview", "medium", "No social-preview tags — the link looks broken when shared on WhatsApp/Facebook")
    if not a.get("_has_h1", True):
        add("no_h1", "low", "No main heading (H1) — weaker for Google and for scanning the page")
    if not a.get("_has_favicon", True):
        add("no_favicon", "low", "No favicon — the little browser-tab icon is missing")
    return f


def audit_one(fetcher: PoliteFetcher, lead: dict, cfg: dict, do_screenshot: bool,
              do_psi: bool = False) -> dict:
    url = lead["website"]
    rd = lead["root_domain"]
    max_pages = cfg.get("crawl", {}).get("max_pages_per_site", 3)

    status, final_url, html = fetcher.get(url)
    https_ok = final_url.lower().startswith("https://") if final_url else False
    weight = len(html.encode("utf-8")) if html else 0

    title_m = TITLE_RE.search(html or "")
    title = re.sub(r"\s+", " ", title_m.group(1)).strip()[:200] if title_m else ""
    gen = GENERATOR_RE.search(html or "")
    gen_content = gen.group(1) if gen else ""
    is_wp = ("wordpress" in gen_content.lower()) or "wp-content" in (html or "") or "wp-json" in (html or "")
    # Core version only from the generator string — never from asset ?ver=.
    wpver_m = WP_VER_RE.search(gen_content) if gen_content else None
    year_m = YEAR_RE.search(html or "")
    imgs = IMG_RE.findall(html or "")
    imgs_no_dims = sum(1 for tag in imgs if not IMG_DIMS_RE.search(tag))

    socials = find_socials(html or "")
    emails = extract_emails(html or "", url)
    do_not_email = bool(NO_MARKETING_RE.search(html or ""))

    # Deep pass: contact/about pages for emails (and more socials) if homepage thin
    if html and (not emails or not any(socials.values())):
        for page_url in contact_links(html, final_url or url, max_pages - 1):
            _, _, page_html = fetcher.get(page_url)
            if not page_html:
                continue
            if not emails:
                emails = extract_emails(page_html, url)
            for k, v in find_socials(page_html).items():
                socials[k] = socials[k] or v
            if NO_MARKETING_RE.search(page_html):
                do_not_email = True
            if emails and all(socials.values()):
                break

    psi = (pagespeed(final_url or url) if (do_psi and status and 200 <= status < 400)
           else {"psi_perf": None, "lcp": None, "cls": None, "tbt": None})

    shot = screenshot(final_url or url, rd) if (do_screenshot and status and 200 <= status < 400) else ""

    a = {
        "http_status": status,
        "final_url": final_url,
        "https_ok": int(https_ok),
        "redirect_chain": "",
        "is_wordpress": int(is_wp),
        "wp_version": wpver_m.group(1) if wpver_m else "",
        "has_viewport": int(bool(VIEWPORT_RE.search(html or ""))),
        "footer_year": int(year_m.group(1)) if year_m else None,
        "page_weight": weight,
        "imgs_no_dims": imgs_no_dims,
        "internal_links": internal_link_count(html or "", final_url or url),
        "has_title": int(bool(title)),
        "title_text": title,
        "has_meta_desc": int(bool(METADESC_RE.search(html or "") or OGDESC_RE.search(html or ""))),
        "has_tel": int(bool(TEL_RE.search(html or "") or TELNUM_RE.search(html or ""))),
        "has_form": int(bool(FORM_RE.search(html or ""))),
        "has_blog": int(bool(BLOG_RE.search(html or ""))),
        # transient design signals (used by build_findings; not persisted as columns)
        "_has_og": bool(OG_RE.search(html or "")),
        "_has_favicon": bool(FAVICON_RE.search(html or "")),
        "_has_h1": bool(H1_RE.search(html or "")),
        "_styles": len(STYLESHEET_RE.findall(html or "")),
        "_dated_markup": bool(DATED_MARKUP_RE.search(html or "")),
        "has_social": int(any(socials.values())),
        "has_schema": int(bool(SCHEMA_RE.search(html or ""))),
        "has_booking": int(bool(BOOKING_RE.search(html or ""))),
        "has_ads_tag": int(bool(ADS_RE.search(html or ""))),
        "instagram": socials["instagram"],
        "facebook": socials["facebook"],
        "linkedin": socials["linkedin"],
        "emails_found": ", ".join(emails),
        "do_not_email": int(do_not_email),
        "screenshot_path": shot,
        **psi,
    }
    a["findings_json"] = build_findings(a, cfg)
    return a


def run(limit: int | None = None, dry_run: bool = False, do_screenshot: bool = True,
        do_psi: bool | None = None) -> int:
    load_env()
    cfg = load_config()
    crawl = cfg.get("crawl", {})
    if do_psi is None:
        do_psi = bool(crawl.get("pagespeed", False))
    if do_psi and not os.environ.get("PSI_KEY", "").strip():
        log.warning("PageSpeed ON but no PSI_KEY set — anonymous quota is throttled; "
                    "results may be empty. Get a free key (see .env.example).")
    fetcher = PoliteFetcher(
        rps=crawl.get("requests_per_second_per_domain", 1),
        timeout=crawl.get("timeout_seconds", 15),
        obey_robots=crawl.get("obey_robots_txt", True),
    )
    db.init_db()
    with db.connect() as conn:
        leads = db.leads_needing(conn, "audit")
    if limit:
        leads = leads[:limit]
    log.info("Auditing %d leads%s", len(leads), " (dry-run)" if dry_run else "")

    done = 0
    for row in leads:
        lead = dict(row)
        a = audit_one(fetcher, lead, cfg, do_screenshot, do_psi=do_psi)
        fcount = len(a["findings_json"])
        log.info("  %s → HTTP %s, HTTPS=%s, PSI=%s, %d findings, email=%s",
                 lead["root_domain"], a["http_status"], a["https_ok"], a["psi_perf"],
                 fcount, a["emails_found"] or "—")
        if not dry_run:
            with db.connect() as conn:
                db.save_audit(conn, lead["id"], a)
                db.set_lead_status(conn, lead["id"], "audited")
        done += 1
    log.info("audit complete: %d processed%s", done, " (dry-run: nothing written)" if dry_run else "")
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit lead websites (free).")
    ap.add_argument("--limit", type=int, help="audit at most N leads")
    ap.add_argument("--dry-run", action="store_true", help="audit + print, write nothing")
    ap.add_argument("--no-screenshot", dest="screenshot", action="store_false",
                    help="skip Playwright screenshots (faster; no browser needed)")
    ap.add_argument("--psi", dest="psi", action="store_true", default=None,
                    help="run PageSpeed Insights (slow; best with a free PSI_KEY)")
    ap.add_argument("--no-psi", dest="psi", action="store_false",
                    help="skip PageSpeed (default; relies on the other fixable signals)")
    a = ap.parse_args()
    run(limit=a.limit, dry_run=a.dry_run, do_screenshot=a.screenshot, do_psi=a.psi)


if __name__ == "__main__":
    sys.exit(main())
