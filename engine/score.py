"""
score.py — the intelligent qualifier. This is where 2000 raw leads become ~20.

Two layers, both pure Python (NO LLM, NO cost):

  1. HARD GATES  — a lead is QUALIFIED only if it clears every gate:
       reachable  ·  not a chain  ·  has a visible fixable problem  ·  can pay.
     Fail any gate → not qualified, never reaches the call sheet.

  2. RANK SCORE (0-100) — qualified leads are ranked so the biggest pain +
     strongest ability-to-pay surface first. The 6 weighted dimensions are
     adapted from opengtm's qualify.py, retuned for AU local businesses.

Output: scores table + a printed top-N "today queue".

    python -m engine.score
    python -m engine.score --dry-run
    python -m engine.score --show 20
"""

from __future__ import annotations

import argparse
import json
import sys

from . import db
from .common import get_logger, load_config, load_exclude_domains

log = get_logger("score")

SEV_POINTS = {"high": 8, "medium": 4, "low": 1}


# ── Hard gates ────────────────────────────────────────────────────────────────
def check_gates(lead: dict, audit: dict, findings: list[dict], cfg: dict,
                excluded: set[str]) -> dict:
    q = cfg.get("qualify", {})
    gates_cfg = q.get("gates", {})
    min_pages = q.get("min_pages_for_pay_signal", 5)
    fixable = set(q.get("fixable_problems", []))
    niche_tiers = cfg.get("niche_tiers", {})

    results: dict[str, dict] = {}

    # 1. reachable
    reachable = bool(audit["http_status"] and 200 <= audit["http_status"] < 400
                     and (audit["has_title"] or audit["page_weight"]))
    results["reachable"] = {"pass": reachable,
                            "why": f"HTTP {audit['http_status']}" + ("" if reachable else " — unreachable/empty")}

    # 2. not a chain / franchise
    not_chain = lead["root_domain"] not in excluded
    results["not_chain"] = {"pass": not_chain,
                            "why": "on exclude list (chain)" if not not_chain else "independent domain"}

    # 3. visible fixable problem
    problem_types = {f["type"] for f in findings}
    hit = sorted(problem_types & fixable)
    has_problem = bool(hit)
    results["fixable_problem"] = {"pass": has_problem,
                                  "why": ("found: " + ", ".join(hit)) if hit else "no sellable problem found"}

    # 4. ability to pay
    has_phone = bool(lead.get("phone"))
    pay_signals = []
    if audit["internal_links"] and audit["internal_links"] >= min_pages:
        pay_signals.append(f"{audit['internal_links']} pages")
    if audit["has_booking"]:
        pay_signals.append("online booking")
    if audit["has_ads_tag"]:
        pay_signals.append("runs ads/pixels")
    if lead.get("niche") in niche_tiers:
        pay_signals.append(f"{lead['niche']} niche")
    can_pay = has_phone and bool(pay_signals)
    results["ability_to_pay"] = {
        "pass": can_pay,
        "why": (("phone + " + ", ".join(pay_signals)) if can_pay
                else ("no phone" if not has_phone else "no spend/size signal")),
    }

    # Only enforce gates that are switched on in config
    enforced = {
        "reachable": gates_cfg.get("require_reachable", True),
        "not_chain": gates_cfg.get("require_not_chain", True),
        "fixable_problem": gates_cfg.get("require_fixable_problem", True),
        "ability_to_pay": gates_cfg.get("require_ability_to_pay", True),
    }
    qualified = all(results[g]["pass"] for g, on in enforced.items() if on)
    return {"qualified": qualified, "gates": results}


# ── Rank dimensions (0-100 total) ─────────────────────────────────────────────
def _ability_to_pay(lead: dict, audit: dict, cfg: dict) -> tuple[int, list[str]]:
    """0-30. Niche LTV tier + budget signals + established-business signals."""
    score, why = 0, []
    tier = cfg.get("niche_tiers", {}).get(lead.get("niche"), 1)
    pts = {3: 12, 2: 8, 1: 4}.get(tier, 4)
    score += pts
    why.append(f"{lead.get('niche','?')} = pay-tier {tier} (+{pts})")
    if audit["has_booking"]:
        score += 6; why.append("online booking (+6)")
    if audit["has_ads_tag"]:
        score += 6; why.append("runs paid ads (+6)")
    if audit["internal_links"] and audit["internal_links"] >= 5:
        score += 3; why.append(f"{audit['internal_links']} pages (+3)")
    rc = lead.get("review_count") or 0
    if rc >= 20:
        score += 3; why.append(f"{rc} reviews (established) (+3)")
    return min(score, 30), why


def _pain_severity(findings: list[dict]) -> tuple[int, list[str]]:
    """0-35. Severity-weighted unique finding types — more pain = better deal."""
    score, why, seen = 0, [], set()
    for f in sorted(findings, key=lambda x: -SEV_POINTS.get(x["severity"], 1)):
        if f["type"] in seen:
            continue
        seen.add(f["type"])
        p = SEV_POINTS.get(f["severity"], 1)
        score += p
        if len(why) < 3:
            why.append(f"{f['severity']}: {f['type']} (+{p})")
    return min(score, 35), why


def _reach_contact(audit: dict) -> tuple[int, list[str]]:
    """0-15. How reachable: published email + click-to-call + contact form."""
    score, why = 0, []
    if audit["emails_found"]:
        score += 8; why.append("published email (+8)")
    if audit["has_tel"]:
        score += 4; why.append("tel link (+4)")
    if audit["has_form"]:
        score += 3; why.append("contact form (+3)")
    return min(score, 15), why


def _digital_maturity(audit: dict) -> tuple[int, list[str]]:
    """0-10. Invests in digital → understands value, easier to sell to."""
    score, why = 0, []
    if audit["has_blog"]:
        score += 4; why.append("blog/news (+4)")
    if audit["has_social"]:
        score += 3; why.append("active social (+3)")
    if audit["has_schema"]:
        score += 3; why.append("schema markup (+3)")
    return min(score, 10), why


def _opportunity(audit: dict, findings: list[dict]) -> tuple[int, list[str]]:
    """0-10. Neglect signals that make the pitch land."""
    score, why = 0, []
    ftypes = {f["type"] for f in findings}
    if "stale_copyright" in ftypes:
        score += 4; why.append("stale footer year (+4)")
    if "outdated_wp" in ftypes:
        score += 3; why.append("outdated WordPress (+3)")
    if audit["psi_perf"] is not None and audit["psi_perf"] < 30:
        score += 3; why.append(f"PSI {audit['psi_perf']} very low (+3)")
    return min(score, 10), why


def _top_problem(findings: list[dict]) -> str:
    if not findings:
        return ""
    best = max(findings, key=lambda f: SEV_POINTS.get(f["severity"], 1))
    return best["detail"]


def score_lead(lead: dict, audit: dict, cfg: dict, excluded: set[str]) -> dict:
    findings = json.loads(audit["findings_json"] or "[]")
    gate = check_gates(lead, audit, findings, cfg, excluded)

    pay, pay_w = _ability_to_pay(lead, audit, cfg)
    pain, pain_w = _pain_severity(findings)
    reach, reach_w = _reach_contact(audit)
    mat, mat_w = _digital_maturity(audit)
    opp, opp_w = _opportunity(audit, findings)
    total = min(pay + pain + reach + mat + opp, 100)

    tier = "hot" if total >= 70 else ("warm" if total >= 45 else "cold")
    reason = "; ".join(pain_w[:2] + pay_w[:1]) or "scored"
    return {
        "score": total,
        "qualified": gate["qualified"],
        "tier": tier,
        "top_problem": _top_problem(findings),
        "gates": gate["gates"],
        "breakdown": {"ability_to_pay": pay, "pain_severity": pain, "reach_contact": reach,
                      "digital_maturity": mat, "opportunity": opp},
        "reason": reason,
    }


def run(dry_run: bool = False, show: int | None = None) -> dict:
    cfg = load_config()
    excluded = load_exclude_domains()
    db.init_db()
    with db.connect() as conn:
        leads = db.leads_needing(conn, "score")
        log.info("Scoring %d audited leads%s", len(leads), " (dry-run)" if dry_run else "")
        qualified = 0
        for row in leads:
            lead = dict(row)
            audit = db.audit_for(conn, lead["id"])
            if not audit:
                continue
            result = score_lead(lead, dict(audit), cfg, excluded)
            if result["qualified"]:
                qualified += 1
            flag = "✓QUALIFIED" if result["qualified"] else "·dropped  "
            failed = [g for g, r in result["gates"].items() if not r["pass"]]
            log.info("  %s %3d/100 [%s] %s%s", flag, result["score"], result["tier"],
                     lead["root_domain"], (" — failed: " + ",".join(failed)) if failed else "")
            if not dry_run:
                db.save_score(conn, lead["id"], result)
                db.set_lead_status(conn, lead["id"], "scored")

    cap = show or cfg.get("daily_claude_leads_cap", 25)
    with db.connect() as conn:
        queue = db.today_queue(conn, cap)
    log.info("── TODAY QUEUE (top %d qualified) ──", len(queue))
    for i, r in enumerate(queue, 1):
        log.info("  %2d. %3d/100 %-28s %s | %s", i, r["score"], r["root_domain"],
                 r["phone"] or "—", (r["top_problem"] or "")[:60])
    log.info("score complete: %d qualified of %d scored%s",
             qualified, len(leads), " (dry-run: nothing written)" if dry_run else "")
    return {"qualified": qualified, "scored": len(leads)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Qualify + rank leads (hard gates + 0-100 score).")
    ap.add_argument("--dry-run", action="store_true", help="score + print, write nothing")
    ap.add_argument("--show", type=int, help="print this many in the today queue")
    a = ap.parse_args()
    run(dry_run=a.dry_run, show=a.show)


if __name__ == "__main__":
    sys.exit(main())
