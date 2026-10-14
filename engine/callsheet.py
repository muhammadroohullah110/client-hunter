"""
callsheet.py — your 7:00 AM screen. Step 2 of the pipeline.

Serves a local, offline-capable web page (stdlib http.server — no Flask, no pip
install) with one card per QUALIFIED lead, best score first:

    business · local time there · click-to-call · opener · top findings ·
    objection notes · one-click outcome buttons (+ keyboard shortcuts).

Outcomes POST straight back to SQLite (and NOT_INTERESTED is appended to
suppression.csv so the lead is never contacted again). Nothing is auto-dialled
or auto-sent — you call, you click.

    python -m engine.callsheet                 # serve at http://localhost:8700
    python -m engine.callsheet --port 8787
    python -m engine.callsheet --limit 25
    python -m engine.callsheet --static        # dump a read-only HTML file

Openers/objections are filled by the Step 3 "morning write step" (write.py).
Until then the sheet shows audit-derived findings + generic per-niche objection
hints, so it is already callable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import db
from .common import SUPPRESSION_CSV, get_logger, load_config

log = get_logger("callsheet")

CITY_TZ = {
    "Brisbane": "Australia/Brisbane", "Gold Coast": "Australia/Brisbane",
    "Sydney": "Australia/Sydney", "Melbourne": "Australia/Melbourne",
    "Perth": "Australia/Perth", "Adelaide": "Australia/Adelaide",
    "Darwin": "Australia/Darwin", "Hobart": "Australia/Hobart",
    "Canberra": "Australia/Sydney",
}
CITY_OFFSET = {  # fallback hours if tzdata/zoneinfo unavailable (no DST)
    "Brisbane": 10, "Gold Coast": 10, "Sydney": 10, "Melbourne": 10,
    "Perth": 8, "Adelaide": 9.5, "Darwin": 9.5, "Hobart": 10, "Canberra": 10,
}

# Generic objection hints per niche, used until Claude writes tailored ones.
NICHE_OBJECTIONS = {
    "dentist": [("We already have someone", "Great — I only fix what's measurably slow; happy to send the 2-min audit."),
                ("No time", "That's exactly why I do it done-for-you in 48 hours, fixed price."),
                ("Send me an email", "Will do — what's the best address? I'll attach the audit.")],
    "physiotherapist": [("We're busy enough", "Then a faster site just protects the bookings you already get."),
                        ("Not interested", "No worries — mind if I send the one-page audit so you have it?"),
                        ("Who are you again", "I'm local, I fix slow clinic websites — found yours loads slowly on mobile.")],
    "accountant": [("It works fine", "On desktop, yes — on mobile it's slow, and that's where clients check."),
                   ("Too expensive", "It's a fixed $[price], one-off — cheaper than one lost client."),
                   ("Email me", "Of course — I'll send the audit with the two issues I found.")],
    "plumber": [("I get enough jobs", "Fair — this just stops the ones Googling you at 11pm bouncing off a slow site."),
                ("Not now", "All good — want the free audit so it's there when you are?"),
                ("How much", "Fixed $[price], done in 48 hours, no lock-in.")],
    "electrician": [("Mate I'm flat out", "Then the site should be pulling its weight — yours is slow on mobile."),
                    ("No thanks", "No worries — I'll text the audit, no obligation."),
                    ("What's it cost", "Fixed $[price] one-off, 48-hour turnaround.")],
}

OUTCOMES = ["NO_ANSWER", "GATEKEEPER", "NOT_INTERESTED", "SEND_AUDIT", "CALLBACK", "SOLD"]


def _local_time(city: str) -> str:
    now_utc = dt.datetime.now(dt.timezone.utc)
    tzname = CITY_TZ.get(city)
    if tzname:
        try:
            from zoneinfo import ZoneInfo
            return now_utc.astimezone(ZoneInfo(tzname)).strftime("%a %I:%M %p")
        except Exception:
            pass
    off = CITY_OFFSET.get(city, 10)
    return (now_utc + dt.timedelta(hours=off)).strftime("%a %I:%M %p") + " (approx)"


def build_cards(conn, cfg: dict, limit: int) -> list[dict]:
    price = cfg.get("offer", {}).get("price_aud", "")
    cards = []
    for r in db.today_queue(conn, limit):
        audit = db.audit_for(conn, r["id"])
        findings = json.loads(audit["findings_json"]) if audit and audit["findings_json"] else []
        findings.sort(key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(f["severity"], 3))
        draft = conn.execute("SELECT * FROM drafts WHERE lead_id=?", (r["id"],)).fetchone()
        objections = NICHE_OBJECTIONS.get(r["niche"], [])
        objections = [(o, a.replace("$[price]", f"${price}")) for o, a in objections]
        last = conn.execute(
            "SELECT status, note, created_at FROM outcomes WHERE lead_id=? ORDER BY id DESC LIMIT 1",
            (r["id"],)).fetchone()
        cards.append({
            "id": r["id"], "name": r["name"] or r["root_domain"], "domain": r["root_domain"],
            "website": r["website"], "phone": r["phone"], "phone_type": r["phone_type"],
            "email": (audit["emails_found"] if audit else "") or r["email"] or "",
            "city": r["city"], "local_time": _local_time(r["city"]), "niche": r["niche"],
            "score": r["score"], "tier": r["tier"],
            "opener": (draft["opener"] if draft and draft["opener"] else ""),
            "findings": findings[:3], "objections": objections,
            "last_outcome": (f"{last['status']} · {last['created_at'][:16]}" if last else ""),
            "do_not_email": bool(audit["do_not_email"]) if audit else False,
        })
    return cards


def append_suppression(domain: str, phone: str, reason: str) -> None:
    import csv
    new = not SUPPRESSION_CSV.exists() or SUPPRESSION_CSV.stat().st_size == 0
    with open(SUPPRESSION_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["root_domain", "phone", "email", "reason", "created_at"])
        w.writerow([domain, phone, "", reason, dt.datetime.now().isoformat(timespec="seconds")])


def record_outcome(lead_id: int, status: str, note: str = "", callback_at: str = "") -> dict:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO outcomes (lead_id, status, note, callback_at, created_at) VALUES (?,?,?,?,?)",
            (lead_id, status, note, callback_at or None, now))
        lead = conn.execute("SELECT root_domain, phone FROM leads WHERE id=?", (lead_id,)).fetchone()
        if status == "NOT_INTERESTED" and lead:
            append_suppression(lead["root_domain"], lead["phone"] or "", note or "said not interested")
            db.set_lead_status(conn, lead_id, "suppressed")
        if status in ("SEND_AUDIT", "SOLD"):
            # mark the email draft ready for the follow-up step (create a stub if none yet)
            exists = conn.execute("SELECT 1 FROM drafts WHERE lead_id=?", (lead_id,)).fetchone()
            if exists:
                conn.execute("UPDATE drafts SET state='ready' WHERE lead_id=?", (lead_id,))
            else:
                conn.execute("INSERT INTO drafts (lead_id, state, created_at) VALUES (?, 'ready', ?)",
                             (lead_id, now))
    return {"ok": True, "lead_id": lead_id, "status": status}


# ── HTML ──────────────────────────────────────────────────────────────────────
def render_html(cards: list[dict], cfg: dict, live: bool = True) -> str:
    biz = html.escape(str(cfg.get("business_name", "CHunter")))
    me = html.escape(str(cfg.get("my_name", "")))
    today = dt.date.today().strftime("%A %d %B %Y")
    sev_color = {"high": "#d7263d", "medium": "#e8870b", "low": "#6b7280"}

    rows = []
    for i, c in enumerate(cards, 1):
        findings_html = "".join(
            f'<li><span class="sev" style="background:{sev_color.get(f["severity"],"#6b7280")}">'
            f'{html.escape(f["severity"])}</span> {html.escape(f["detail"])}</li>'
            for f in c["findings"])
        obj_html = "".join(
            f'<li><b>“{html.escape(o)}”</b> → {html.escape(a)}</li>' for o, a in c["objections"])
        opener = html.escape(c["opener"]) if c["opener"] else \
            '<em class="pending">Opener pending — run the morning write step (Step 3).</em>'
        phone = html.escape(c["phone"] or "")
        tel = f'<a class="tel" href="tel:{phone}">{phone}</a>' if phone else '<span class="muted">no phone</span>'
        mobile_warn = ' <span class="warn">⚠ mobile — CHECK_DNCR</span>' if c["phone_type"] == "mobile" else ""
        dne = ' <span class="warn">✉ do-not-email</span>' if c["do_not_email"] else ""
        last = f'<div class="last">last: {html.escape(c["last_outcome"])}</div>' if c["last_outcome"] else ""
        email = f'<span class="muted">{html.escape(c["email"])}</span>' if c["email"] else ""
        rows.append(f"""
<div class="card" id="card-{c['id']}" data-id="{c['id']}">
  <div class="head">
    <div class="rank">{i}</div>
    <div class="who">
      <h2>{html.escape(c['name'])} <span class="score {c['tier']}">{c['score']}/100 · {c['tier']}</span></h2>
      <div class="meta">{html.escape(c['city'])} · <b>{c['local_time']}</b> · {html.escape(c['niche'])}
        · <a href="{html.escape(c['website'])}" target="_blank" rel="noopener">{html.escape(c['domain'])}</a></div>
    </div>
    <div class="call">{tel}{mobile_warn}{dne}<br>{email}</div>
  </div>
  <div class="body">
    <div class="opener"><h3>Opener</h3><p>{opener}</p></div>
    <div class="cols">
      <div><h3>Top findings</h3><ul class="findings">{findings_html or '<li>—</li>'}</ul></div>
      <div><h3>Objections</h3><ul class="obj">{obj_html or '<li>—</li>'}</ul></div>
    </div>
    {last}
    <div class="actions">
      <button data-o="NO_ANSWER"      title="1">No answer (1)</button>
      <button data-o="GATEKEEPER"     title="2">Gatekeeper (2)</button>
      <button data-o="NOT_INTERESTED" class="danger" title="3">Not interested (3)</button>
      <button data-o="SEND_AUDIT"     class="go" title="4">Send audit (4)</button>
      <button data-o="CALLBACK"       title="5">Callback… (5)</button>
      <button data-o="SOLD"           class="sold" title="6">SOLD 🎉 (6)</button>
    </div>
  </div>
</div>""")

    disabled_note = "" if live else (
        '<div class="offline">Read-only export — outcome buttons work only when served with '
        '<code>python -m engine.callsheet</code>.</div>')

    script = """
<script>
const LIVE = %s;
let current = 0;
const cards = [...document.querySelectorAll('.card')];
function focusCard(n){ current = Math.max(0, Math.min(cards.length-1, n));
  cards.forEach((c,i)=>c.classList.toggle('active', i===current));
  cards[current]?.scrollIntoView({behavior:'smooth', block:'center'}); }
async function logOutcome(id, outcome, btn){
  if(!LIVE){ alert('Read-only export. Serve with: python -m engine.callsheet'); return; }
  let note='', callback='';
  if(outcome==='CALLBACK'){ callback = prompt('Callback when? (e.g. 2026-10-15 14:00)')||''; if(!callback) return; }
  if(outcome==='NOT_INTERESTED'){ if(!confirm('Add to suppression — never contact again?')) return; }
  const r = await fetch('/outcome', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({lead_id:id, status:outcome, note, callback_at:callback})});
  if(r.ok){ const card=document.getElementById('card-'+id);
    card.classList.add('done'); card.querySelector('.actions').insertAdjacentHTML('beforeend',
      '<span class=\\"logged\\">✓ '+outcome+'</span>'); }
  else alert('Failed to log — is the server still running?');
}
document.addEventListener('click', e=>{ const b=e.target.closest('button[data-o]'); if(!b) return;
  const id=+b.closest('.card').dataset.id; logOutcome(id, b.dataset.o, b); });
document.addEventListener('keydown', e=>{
  if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA') return;
  if(e.key==='j'){ focusCard(current+1); } else if(e.key==='k'){ focusCard(current-1); }
  else if('123456'.includes(e.key)){ const b=cards[current]?.querySelectorAll('button[data-o]')[+e.key-1]; b?.click(); }
});
focusCard(0);
</script>""" % ("true" if live else "false")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CHunter Call Sheet — {today}</title>
<style>
:root{{--bg:#0f1115;--card:#1a1d24;--line:#2a2f3a;--fg:#e8eaed;--muted:#9aa0aa;--accent:#4ade80;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);
 font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:0 16px 80px}}
header{{position:sticky;top:0;background:var(--bg);padding:16px 0;border-bottom:1px solid var(--line);z-index:5}}
header h1{{margin:0;font-size:20px}} header .sub{{color:var(--muted);font-size:13px}}
.offline{{background:#3a2a00;color:#ffd27a;padding:8px 12px;border-radius:8px;margin:12px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:14px 0;overflow:hidden}}
.card.active{{border-color:var(--accent);box-shadow:0 0 0 2px rgba(74,222,128,.15)}}
.card.done{{opacity:.55}}
.head{{display:flex;gap:14px;align-items:flex-start;padding:14px 16px;background:#20242d}}
.rank{{font-size:22px;font-weight:700;color:var(--muted);min-width:28px}}
.who{{flex:1}} .who h2{{margin:0;font-size:17px}}
.score{{font-size:12px;padding:2px 8px;border-radius:20px;background:#333;margin-left:6px;vertical-align:middle}}
.score.hot{{background:#7f1d1d}} .score.warm{{background:#78501b}} .score.cold{{background:#374151}}
.meta{{color:var(--muted);font-size:13px;margin-top:3px}} .meta a{{color:#7fb4ff}}
.call{{text-align:right;font-size:14px}} .tel{{font-size:19px;font-weight:700;color:var(--accent);text-decoration:none}}
.warn{{color:#ffb84d;font-size:12px}} .muted{{color:var(--muted);font-size:12px}}
.body{{padding:14px 16px}} h3{{margin:12px 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
.opener p{{margin:0;font-size:16px;background:#12151b;padding:10px 12px;border-left:3px solid var(--accent);border-radius:6px}}
.pending{{color:#ffb84d}}
.cols{{display:flex;gap:20px;flex-wrap:wrap}} .cols>div{{flex:1;min-width:240px}}
ul{{margin:0;padding-left:18px}} li{{margin:4px 0}}
.sev{{color:#fff;font-size:10px;padding:1px 6px;border-radius:4px;text-transform:uppercase;margin-right:4px}}
.last{{color:var(--muted);font-size:12px;margin-top:10px}}
.actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}
button{{background:#2a2f3a;color:var(--fg);border:1px solid var(--line);padding:9px 12px;border-radius:9px;cursor:pointer;font-size:13px}}
button:hover{{border-color:var(--accent)}}
button.danger{{background:#4a1d1d}} button.go{{background:#1d3a4a}} button.sold{{background:#14532d;font-weight:700}}
.logged{{color:var(--accent);align-self:center;font-weight:700;margin-left:6px}}
</style></head><body>
<header><h1>☎ Call Sheet — {biz}</h1>
<div class="sub">{today} · {len(cards)} qualified leads · ranked best-first · {html.escape(me)}
 &nbsp;|&nbsp; keys: <b>j/k</b> move · <b>1–6</b> log outcome</div></header>
{disabled_note}
{''.join(rows) or '<p style="color:#9aa0aa;margin-top:30px">No qualified leads yet. Run the nightly pipeline: <code>python run_step1.py</code></p>'}
{script}
</body></html>"""


# ── Server ──────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    cfg: dict = {}
    limit: int = 25

    def log_message(self, *a):  # quiet default logging
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/callsheet.html"):
            return self._send(404, "not found", "text/plain")
        with db.connect() as conn:
            cards = build_cards(conn, self.cfg, self.limit)
        self._send(200, render_html(cards, self.cfg, live=True))

    def do_POST(self):
        if self.path != "/outcome":
            return self._send(404, "not found", "text/plain")
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            res = record_outcome(int(payload["lead_id"]), str(payload["status"]),
                                  payload.get("note", ""), payload.get("callback_at", ""))
            log.info("logged %s for lead %s", payload["status"], payload["lead_id"])
            self._send(200, json.dumps(res), "application/json")
        except Exception as e:
            log.error("outcome failed: %s", e)
            self._send(400, json.dumps({"ok": False, "error": str(e)}), "application/json")


def serve(port: int, limit: int, open_browser: bool = True) -> None:
    db.init_db()
    Handler.cfg = load_config()
    Handler.limit = limit
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    log.info("Call sheet live at %s  (Ctrl+C to stop)", url)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("stopped")
        srv.shutdown()


def main() -> None:
    ap = argparse.ArgumentParser(description="CHunter 7 AM call sheet (local server).")
    ap.add_argument("--port", type=int, default=8700)
    ap.add_argument("--limit", type=int, default=None, help="max cards (default: daily_claude_leads_cap)")
    ap.add_argument("--no-open", dest="open", action="store_false", help="don't auto-open the browser")
    ap.add_argument("--static", action="store_true", help="write a read-only out/callsheet.html and exit")
    a = ap.parse_args()
    cfg = load_config()
    limit = a.limit or cfg.get("daily_claude_leads_cap", 25)

    if a.static:
        db.init_db()
        with db.connect() as conn:
            cards = build_cards(conn, cfg, limit)
        from .common import OUT_DIR
        path = OUT_DIR / "callsheet.html"
        path.write_text(render_html(cards, cfg, live=False), encoding="utf-8")
        log.info("wrote %s (%d cards, read-only)", path, len(cards))
        return
    serve(a.port, limit, open_browser=a.open)


if __name__ == "__main__":
    sys.exit(main())
