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
WPVER_RE = re.compile(r"(?:wp-embed\.min\.js|ver=)(\d+\.\d+(?:\.\d+)?)", re.I)
TEL_RE = re.compile(r'href=["\']tel:', re.I)
FORM_RE = re.compile(r"<form[\s>]", re.I)
IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
IMG_DIMS_RE = re.compile(r"\b(width|height)\s*=", re.I)
SCHEMA_RE = re.compile(r'application/ld\+json|itemscope|itemtype=', re.I)
YEAR_RE = re.compile(r"(?:©|&copy;|copyright)[^0-9]{0,20}(20\d{2})", re.I)

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
    if a["is_wordpress"] and a["wp_version"]:
        add("outdated_wp", "medium", f"WordPress version {a['wp_version']} exposed (update/security risk)")
    if a["imgs_no_dims"] and a["imgs_no_dims"] >= 5:
        add("images_no_dims", "low", f"{a['imgs_no_dims']} images without width/height (layout shift)")
    if not a["has_tel"]:
        add("no_tel_link", "low", "No click-to-call tel: link on homepage")
    if not a["has_form"]:
        add("no_contact_form", "low", "No contact form found on homepage")
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
    is_wp = bool(gen and "wordpress" in gen.group(1).lower()) or "wp-content" in (html or "") or "wp-json" in (html or "")
    wpver_m = WPVER_RE.search(html or "") if is_wp else None
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
        "has_meta_desc": int(bool(METADESC_RE.search(html or ""))),
        "has_tel": int(bool(TEL_RE.search(html or ""))),
        "has_form": int(bool(FORM_RE.search(html or ""))),
        "has_blog": int(bool(BLOG_RE.search(html or ""))),
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
