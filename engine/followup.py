"""
followup.py — Step 4. Prepares follow-ups; never sends anything automatically.

Two jobs:
  1. DRAFTS: for leads you marked SEND_AUDIT or SOLD (drafts.state='ready'),
     write a ready-to-send .eml file (opens in Outlook / Gmail / any mail app)
     with the one-page audit attached. You review and hit send. Nothing leaves
     your machine on its own.
  2. REQUEUE: NO_ANSWER leads come back once after 2 business days (max 3 tries
     total, then dropped). CALLBACK leads surface on their day. Produces a
     "due today" list the call sheet can pick up.

Optional: if you drop Gmail OAuth creds in gmail_credentials.json, pass --gmail
to create real Gmail drafts instead of .eml files. Still never auto-sends.

    python -m engine.followup                 # make .eml drafts + show due-today
    python -m engine.followup --drafts-only
    python -m engine.followup --requeue-only
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from email.message import EmailMessage
from pathlib import Path

from . import db
from .common import OUT_DIR, get_logger, load_config

log = get_logger("followup")

MAX_ATTEMPTS = 3
REQUEUE_BUSINESS_DAYS = 2


def _add_business_days(start: dt.date, n: int) -> dt.date:
    d, added = start, 0
    while added < n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:  # Mon–Fri
            added += 1
    return d


def _build_eml(lead: dict, draft: dict, cfg: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{cfg.get('my_name','')} <{cfg.get('my_email','')}>"
    to = (lead.get("email") or "").split(",")[0].strip()
    msg["To"] = to
    msg["Subject"] = draft.get("email_subject") or f"Quick note about {lead['name']}'s website"
    msg.set_content(draft.get("email_body") or "")
    # Attach the one-page audit if it exists
    pdf = draft.get("pdf_path")
    if pdf and Path(pdf).exists():
        data = Path(pdf).read_bytes()
        msg.add_attachment(data, maintype="text", subtype="html",
                           filename=f"{lead['root_domain']}-audit.html")
    return msg


def make_drafts(use_gmail: bool = False) -> int:
    cfg = load_config()
    out_dir = OUT_DIR / dt.date.today().isoformat() / "drafts"
    made = 0
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT d.*, l.name, l.root_domain, l.email FROM drafts d "
            "JOIN leads l ON l.id=d.lead_id WHERE d.state='ready'").fetchall()
        for r in rows:
            d = dict(r)
            if not (d.get("email_subject") and d.get("email_body")) or \
               d.get("email_body", "").startswith("(skipped"):
                log.info("  skip %s (no email / do-not-email)", d["root_domain"])
                continue
            to = (d.get("email") or "").split(",")[0].strip()
            if not to:
                log.info("  skip %s (no published email address)", d["root_domain"])
                continue
            msg = _build_eml(d, d, cfg)
            if use_gmail:
                ok = _gmail_draft(msg)
                state = "drafted_gmail" if ok else "ready"
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"{d['root_domain']}.eml"
                path.write_bytes(bytes(msg))
                log.info("  draft → %s  (to %s)", path.name, to)
                state = "drafted"
            if state.startswith("drafted"):
                conn.execute("UPDATE drafts SET state=? WHERE lead_id=?", (state, d["lead_id"]))
                made += 1
    log.info("drafts complete: %d email(s) prepared (never auto-sent)", made)
    return made


def _gmail_draft(msg: EmailMessage) -> bool:
    """Create a Gmail draft via the user's own OAuth creds. Best-effort; returns
    False (so we fall back to .eml) if the libraries/creds aren't present."""
    try:
        import base64
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except Exception:
        log.warning("Gmail libraries not installed — falling back to .eml. "
                    "pip install google-api-python-client google-auth-oauthlib")
        return False
    creds_path = Path("gmail_token.json")
    if not creds_path.exists():
        log.warning("gmail_token.json not found — falling back to .eml (see README Gmail setup)")
        return False
    try:
        creds = Credentials.from_authorized_user_file(str(creds_path))
        service = build("gmail", "v1", credentials=creds)
        raw = base64.urlsafe_b64encode(bytes(msg)).decode()
        service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
        return True
    except Exception as e:
        log.warning("Gmail draft failed (%s) — falling back to .eml", e)
        return False


def requeue() -> list[dict]:
    """Apply NO_ANSWER requeue + surface CALLBACKs. Returns due-today items."""
    today = dt.date.today()
    due: list[dict] = []
    with db.connect() as conn:
        # latest outcome per lead
        rows = conn.execute("""
            SELECT o.lead_id, o.status, o.callback_at, o.created_at, l.name, l.root_domain,
                   (SELECT COUNT(*) FROM outcomes o2 WHERE o2.lead_id=o.lead_id AND o2.status='NO_ANSWER') AS no_ans
            FROM outcomes o JOIN leads l ON l.id=o.lead_id
            WHERE o.id IN (SELECT MAX(id) FROM outcomes GROUP BY lead_id)
        """).fetchall()
        for r in rows:
            d = dict(r)
            if d["status"] == "CALLBACK" and d["callback_at"]:
                cb = d["callback_at"][:10]
                if cb <= today.isoformat():
                    due.append({**d, "reason": f"callback due ({d['callback_at']})"})
            elif d["status"] == "NO_ANSWER":
                if d["no_ans"] >= MAX_ATTEMPTS:
                    db.set_lead_status(conn, d["lead_id"], "scored")  # exhausted; drop from active
                    continue
                last = dt.date.fromisoformat(d["created_at"][:10])
                nextd = _add_business_days(last, REQUEUE_BUSINESS_DAYS)
                if nextd <= today:
                    due.append({**d, "reason": f"retry #{d['no_ans']+1} (last {d['created_at'][:10]})"})
    log.info("── DUE TODAY (%d) ──", len(due))
    for d in due:
        log.info("  %-28s %s", d["root_domain"], d["reason"])
    return due


def run(drafts: bool = True, do_requeue: bool = True, use_gmail: bool = False) -> None:
    db.init_db()
    if drafts:
        make_drafts(use_gmail=use_gmail)
    if do_requeue:
        requeue()


def main() -> None:
    ap = argparse.ArgumentParser(description="Prepare follow-up drafts + requeue (no auto-send).")
    ap.add_argument("--drafts-only", action="store_true")
    ap.add_argument("--requeue-only", action="store_true")
    ap.add_argument("--gmail", action="store_true", help="create Gmail drafts if creds present")
    a = ap.parse_args()
    run(drafts=not a.requeue_only, do_requeue=not a.drafts_only, use_gmail=a.gmail)


if __name__ == "__main__":
    sys.exit(main())
