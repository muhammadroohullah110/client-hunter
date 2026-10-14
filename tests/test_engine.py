"""
Tests for audit parsing + scoring against 5 saved sample HTML pages.
Run:  python -m pytest tests/ -q     (or:  python tests/test_engine.py)

No network: we feed saved HTML straight into the parsing helpers and assert on
the derived signals, findings, gates, and rank score.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import audit, score  # noqa: E402
from engine.common import normalize_au_phone, root_domain  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
CFG = {
    "qualify": {
        "gates": {"require_reachable": True, "require_not_chain": True,
                  "require_fixable_problem": True, "require_ability_to_pay": True},
        "min_pages_for_pay_signal": 5,
        "fixable_problems": ["low_psi", "slow_lcp", "no_https", "no_viewport",
                             "stale_copyright", "outdated_wp"],
        "psi_fail_threshold": 50, "lcp_fail_seconds": 4.0, "copyright_stale_years": 2,
    },
    "niche_tiers": {"dentist": 3, "physiotherapist": 3, "accountant": 3,
                    "electrician": 2, "plumber": 2},
    "crawl": {"max_pages_per_site": 3},
}


def _html(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _parse(name: str, url: str, status=200) -> dict:
    """Mimic audit_one's parsing on saved HTML (no network)."""
    html = _html(name)
    final = url.replace("http://", "https://")
    a = {
        "http_status": status, "final_url": final,
        "https_ok": int(final.startswith("https://")), "redirect_chain": "",
        "is_wordpress": int("wp-content" in html or "WordPress" in html),
        "wp_version": (audit.WPVER_RE.search(html).group(1) if audit.WPVER_RE.search(html) else ""),
        "has_viewport": int(bool(audit.VIEWPORT_RE.search(html))),
        "footer_year": (int(audit.YEAR_RE.search(html).group(1)) if audit.YEAR_RE.search(html) else None),
        "page_weight": len(html.encode()),
        "imgs_no_dims": sum(1 for t in audit.IMG_RE.findall(html) if not audit.IMG_DIMS_RE.search(t)),
        "internal_links": audit.internal_link_count(html, final),
        "has_title": int(bool(audit.TITLE_RE.search(html))),
        "title_text": "",
        "has_meta_desc": int(bool(audit.METADESC_RE.search(html))),
        "has_tel": int(bool(audit.TEL_RE.search(html))),
        "has_form": int(bool(audit.FORM_RE.search(html))),
        "has_blog": int(bool(audit.BLOG_RE.search(html))),
        "has_social": int(any(audit.find_socials(html).values())),
        "has_schema": int(bool(audit.SCHEMA_RE.search(html))),
        "has_booking": int(bool(audit.BOOKING_RE.search(html))),
        "has_ads_tag": int(bool(audit.ADS_RE.search(html))),
        "emails_found": ", ".join(audit.extract_emails(html, url)),
        "do_not_email": int(bool(audit.NO_MARKETING_RE.search(html))),
        "psi_perf": None, "lcp": None, "cls": None, "tbt": None,
    }
    a["findings_json"] = json.dumps(audit.build_findings(a, CFG))
    return a


# ── Phone + domain helpers ────────────────────────────────────────────────────
def test_phone_classification():
    assert normalize_au_phone("07 3123 4567") == ("0731234567", "landline")
    assert normalize_au_phone("0412 345 678") == ("0412345678", "mobile")
    assert normalize_au_phone("+61 7 3123 4567") == ("0731234567", "landline")
    assert normalize_au_phone("1300 123 456")[1] == "national"
    assert normalize_au_phone("")[1] == "none"


def test_root_domain_au():
    assert root_domain("https://www.brightsmile.com.au/about") == "brightsmile.com.au"
    assert root_domain("http://joesplumbing.net.au") == "joesplumbing.net.au"


# ── Email extraction (junk filtering + on-site ranking) ───────────────────────
def test_email_junk_filtered_and_onsite_wins():
    emails = audit.extract_emails(_html("junk_emails.html"), "http://gcelectrical.com.au")
    assert emails and emails[0] == "info@gcelectrical.com.au"
    assert "name@example.com" not in emails
    assert "you@yourdomain.com" not in emails


def test_socials_skip_sharer():
    s = audit.find_socials(_html("junk_emails.html"))
    assert s["facebook"].endswith("gcelectricalqld")  # not sharer.php


# ── Findings parsing ───────────────────────────────────────────────────────────
def test_good_site_few_findings():
    a = _parse("good_modern.html", "http://brightsmile.com.au")
    types = {f["type"] for f in json.loads(a["findings_json"])}
    assert "no_https" not in types and "no_viewport" not in types
    assert a["has_booking"] and a["has_social"] and a["has_schema"]
    assert a["internal_links"] >= 5


def test_old_wordpress_flags():
    a = _parse("old_wordpress.html", "http://joesplumbing.net.au")
    types = {f["type"] for f in json.loads(a["findings_json"])}
    assert "outdated_wp" in types and a["wp_version"] == "4.9.8"
    assert "stale_copyright" in types          # 2015
    assert "no_viewport" in types
    assert "images_no_dims" in types


def test_no_viewport_meta_flags():
    a = _parse("no_viewport_no_meta.html", "http://adelaideacct.com.au")
    types = {f["type"] for f in json.loads(a["findings_json"])}
    assert "no_viewport" in types and "no_meta_description" in types


def test_no_marketing_sets_do_not_email():
    a = _parse("no_marketing.html", "http://perthphysio.com.au")
    assert a["do_not_email"] == 1


# ── Scoring + gates ────────────────────────────────────────────────────────────
def test_qualified_old_wordpress_plumber():
    a = _parse("old_wordpress.html", "http://joesplumbing.net.au")
    lead = {"root_domain": "joesplumbing.net.au", "niche": "plumber",
            "phone": "0412345678", "review_count": 0}
    r = score.score_lead(lead, a, CFG, excluded=set())
    assert r["qualified"] is True            # reachable + not chain + outdated_wp + phone+niche
    assert r["score"] > 0 and r["top_problem"]


def test_good_modern_site_not_qualified_no_problem():
    a = _parse("good_modern.html", "http://brightsmile.com.au")
    # Force the "clean" case: no fixable problems present → ability high but gate fails
    lead = {"root_domain": "brightsmile.com.au", "niche": "dentist",
            "phone": "0731234567", "review_count": 50}
    r = score.score_lead(lead, a, CFG, excluded=set())
    assert r["gates"]["fixable_problem"]["pass"] is False
    assert r["qualified"] is False           # nothing to sell = not a lead


def test_chain_domain_gated_out():
    a = _parse("old_wordpress.html", "http://pacificsmiles.com.au")
    lead = {"root_domain": "pacificsmiles.com.au", "niche": "dentist",
            "phone": "0731234567", "review_count": 0}
    r = score.score_lead(lead, a, CFG, excluded={"pacificsmiles.com.au"})
    assert r["gates"]["not_chain"]["pass"] is False
    assert r["qualified"] is False


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} tests passed")
    sys.exit(0 if passed == len(fns) else 1)
