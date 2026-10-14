#!/usr/bin/env python3
"""
run_step1.py — the nightly brain: find → audit → score, end to end.

This is the free, no-LLM pipeline that runs while you sleep (Windows Task
Scheduler). It turns thousands of raw businesses into a short ranked queue of
qualified leads. Claude only touches the survivors, in the morning.

    python run_step1.py                      # full run, respects config.yaml
    python run_step1.py --limit 20           # cap leads found (testing)
    python run_step1.py --no-screenshot      # skip Playwright
    python run_step1.py --dry-run            # fetch + score + print, write nothing
"""
import argparse
import sys

from engine import audit, find, score
from engine.common import get_logger

log = get_logger("run")


def main() -> int:
    ap = argparse.ArgumentParser(description="CHunter step 1: find + audit + score.")
    ap.add_argument("--city", action="append")
    ap.add_argument("--niche", action="append")
    ap.add_argument("--limit", type=int, help="cap leads found (testing)")
    ap.add_argument("--no-screenshot", dest="screenshot", action="store_false")
    ap.add_argument("--psi", dest="psi", action="store_true", default=None,
                    help="run PageSpeed Insights (slow; needs a free PSI_KEY to be useful)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    log.info("═══ STEP 1: FIND ═══")
    find.find(cities=a.city, niches=a.niche, limit=a.limit, dry_run=a.dry_run)
    if a.dry_run:
        log.info("Dry-run: stopping after find (nothing stored to audit).")
        return 0

    log.info("═══ STEP 1: AUDIT ═══")
    audit.run(limit=a.limit, do_screenshot=a.screenshot, do_psi=a.psi)

    log.info("═══ STEP 1: SCORE ═══")
    score.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
