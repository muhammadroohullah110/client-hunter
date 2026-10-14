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

from engine import audit, callsheet, outreach, score  # noqa: E402
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
        "wp_version": (audit.WP_VER_RE.search(html).group(1) if audit.WP_VER_RE.search(html) else ""),
        "_has_og": bool(audit.OG_RE.search(html)), "_has_favicon": bool(audit.FAVICON_RE.search(html)),
        "_has_h1": bool(audit.H1_RE.search(html)), "_styles": len(audit.STYLESHEET_RE.findall(html)),
        "_dated_markup": bool(audit.DATED_MARKUP_RE.search(html)),
        "has_viewport": int(bool(audit.VIEWPORT_RE.search(html))),
        "footer_year": (int(audit.YEAR_RE.search(html).group(1)) if audit.YEAR_RE.search(html) else None),
        "page_weight": len(html.encode()),
        "imgs_no_dims": sum(1 for t in audit.IMG_RE.findall(html) if not audit.IMG_DIMS_RE.search(t)),
        "internal_links": audit.internal_link_count(html, final),
        "has_title": int(bool(audit.TITLE_RE.search(html))),
        "title_text": "",
        "has_meta_desc": int(bool(audit.METADESC_RE.search(html) or audit.OGDESC_RE.search(html))),
        "has_tel": int(bool(audit.TEL_RE.search(html) or audit.TELNUM_RE.search(html))),
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


# ── Auditor accuracy fixes (the false-positive bug + design detection) ─────────
def _findings_for(html_extra: str, base="good_modern.html") -> set:
    """Build findings from a good base page plus some injected HTML."""
    import json as _json
    html = _html(base).replace("</body>", html_extra + "</body>")
    final = "https://x.com/"
    a = {"http_status": 200, "final_url": final, "https_ok": 1, "redirect_chain": "",
         "is_wordpress": int("wordpress" in html.lower()),
         "wp_version": (audit.WP_VER_RE.search(html).group(1) if audit.WP_VER_RE.search(html) else ""),
         "has_viewport": 1, "footer_year": 2026, "page_weight": len(html), "imgs_no_dims": 0,
         "internal_links": 6, "has_title": 1, "title_text": "x", "has_meta_desc": 1,
         "has_tel": 1, "has_form": 1, "has_blog": 0, "has_social": 0, "has_schema": 0,
         "has_booking": 0, "has_ads_tag": 0, "emails_found": "", "do_not_email": 0,
         "psi_perf": None, "lcp": None, "cls": None, "tbt": None,
         "_has_og": bool(audit.OG_RE.search(html)), "_has_favicon": bool(audit.FAVICON_RE.search(html)),
         "_has_h1": bool(audit.H1_RE.search(html)), "_styles": len(audit.STYLESHEET_RE.findall(html)),
         "_dated_markup": bool(audit.DATED_MARKUP_RE.search(html))}
    return {f["type"] for f in audit.build_findings(a, CFG)}


def test_plugin_ver_not_misread_as_wordpress_core():
    # The exact bug: an asset ?ver=7.1.3 must NOT become "WordPress 7.1.3 outdated".
    types = _findings_for('<link href="/style.css?ver=7.1.3"><script src="x.js?ver=7.0.4"></script>')
    assert "outdated_wp" not in types


def test_modern_wordpress_not_flagged_outdated():
    types = _findings_for('<meta name="generator" content="WordPress 6.5.2">')
    assert "outdated_wp" not in types          # 6.x is current — not a problem


def test_old_wordpress_core_still_flagged():
    types = _findings_for('<meta name="generator" content="WordPress 4.9.8">')
    assert "outdated_wp" in types              # major < 6 — genuinely old


def test_design_dated_markup_detected():
    types = _findings_for('<table width="800"><font color="red">old</font></table>')
    assert "dated_design" in types


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


# ── Call sheet (pure render, no DB) ───────────────────────────────────────────
def _fake_card():
    return {
        "id": 1, "name": "Warner Lakes Dental", "domain": "warnerlakesdental.com.au",
        "website": "https://warnerlakesdental.com.au", "phone": "0734480162",
        "phone_type": "landline", "email": "info@warnerlakesdental.com.au",
        "city": "Brisbane", "local_time": "Wed 03:00 PM", "niche": "dentist",
        "score": 58, "tier": "warm", "opener": "",
        "findings": [{"type": "outdated_wp", "severity": "medium", "detail": "WordPress 3.7.1 exposed"}],
        "objections": [("We already have someone", "I only fix what's measurably slow.")],
        "last_outcome": "", "do_not_email": False,
    }


def test_callsheet_renders_card_and_tellink():
    html = callsheet.render_html([_fake_card()], {"business_name": "Acme", "my_name": "Me",
                                                   "offer": {"price_aud": 249}}, live=True)
    assert 'href="tel:0734480162"' in html
    assert "Warner Lakes Dental" in html
    assert "58/100" in html
    assert "WordPress 3.7.1 exposed" in html
    assert "const LIVE = true" in html


def test_callsheet_mobile_flagged_and_price_substituted():
    c = _fake_card()
    c["phone_type"] = "mobile"
    c["objections"] = [("How much", "Fixed $[price] one-off.")]
    # price substitution happens in build_cards; emulate it here
    c["objections"] = [(o, a.replace("$[price]", "$249")) for o, a in c["objections"]]
    html = callsheet.render_html([c], {"offer": {"price_aud": 249}}, live=False)
    assert "CHECK_DNCR" in html          # mobile warning shown
    assert "$249" in html
    assert "const LIVE = false" in html  # read-only export disables logging


def test_callsheet_objection_bank_has_all_niches():
    for niche in ("dentist", "physiotherapist", "accountant", "plumber", "electrician"):
        assert niche in callsheet.NICHE_OBJECTIONS and callsheet.NICHE_OBJECTIONS[niche]


# ── Outreach frameworks (trained from the notes) ──────────────────────────────
def test_subject_is_curiosity_and_facts_only():
    subj, opening = outreach.pick_subject("outdated_wp", "Warner Lakes Dental")
    assert "Warner Lakes Dental" in subj
    assert subj == "Warner Lakes Dental — this is being left on the table"
    assert "old software" in opening.lower()
    # a finding type we don't have a pattern for falls back cleanly
    assert outreach.pick_subject("something_new", "Acme")[0].startswith("The good news")


def test_dm_trojan_horse_then_risk_reversal():
    dm = outreach.build_dm("Sam", "Bulimba Dental", "low_psi")
    assert dm["trojan_horse"].startswith("Hey Sam")
    assert "Bulimba Dental" in dm["pitch"]
    assert "don't pay" in dm["pitch"]            # risk reversal present
    assert "slow speed" in dm["pitch"]           # maps the real finding
    # guarantee can be turned off
    assert "don't pay" not in outreach.build_dm("Sam", "X", "low_psi", offer_guarantee=False)["pitch"]


def test_universal_objections_substitute_price_and_hours():
    objs = outreach.universal_objections(249, 48)
    joined = " ".join(a for _, a in objs)
    assert "$249" in joined and "48 hours" in joined
    assert "{price}" not in joined and "{hours}" not in joined
    assert any("agency" in o.lower() for o, _ in objs)   # the big one is covered


def test_call_stages_cover_the_arc():
    titles = " ".join(t for t, _ in outreach.CALL_STAGES).lower()
    for beat in ("tension", "credibility", "problem", "offer", "close"):
        assert beat in titles


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
