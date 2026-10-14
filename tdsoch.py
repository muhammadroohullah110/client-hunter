#!/usr/bin/env python3
"""
TDSOCH — The Damn System Of Client Hunting.
One command to rule the whole pipeline.

    python tdsoch.py run            # nightly brain: find -> audit -> score (free, no LLM)
    python tdsoch.py write          # draft openers + emails + audits for the queue
    python tdsoch.py serve          # open the web app (Dashboard / Call Sheet / Leads)
    python tdsoch.py followup       # prepare .eml drafts + requeue (never auto-sends)
    python tdsoch.py dashboard      # print funnel metrics + write out/dashboard.html
    python tdsoch.py deliver --lead 12            # fix playbook for a SOLD lead
    python tdsoch.py morning        # write + serve (your 7 AM one-liner)

Pass through flags, e.g.:  python tdsoch.py run --city Brisbane --niche dentist --limit 20 --no-screenshot
"""
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    cmd, rest = sys.argv[1], sys.argv[2:]
    sys.argv = [sys.argv[0], *rest]  # hand remaining flags to the submodule

    if cmd == "run":
        import run_step1
        return run_step1.main()
    if cmd == "write":
        from engine import write
        return write.main()
    if cmd == "serve":
        from engine import webapp
        return webapp.main()
    if cmd == "followup":
        from engine import followup
        return followup.main()
    if cmd == "dashboard":
        from engine import dashboard
        return dashboard.run()
    if cmd == "deliver":
        from engine import deliver
        return deliver.main()
    if cmd == "morning":
        from engine import write, webapp
        write.run()
        return webapp.main()
    print(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
