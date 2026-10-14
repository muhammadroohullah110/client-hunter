"""
webui.py — TDSOCH's look & feel. One place owns the app shell (sidebar, theme,
shared JS) and every page body (dashboard, call sheet, leads, lead detail), so
the whole system reads as one product.

TDSOCH — The Damn System Of Client Hunting.
"""

from __future__ import annotations

import datetime as dt
import html
import json

from . import db

BRAND = "TDSOCH"
TAGLINE = "The Damn System Of Client Hunting"

NAV = [("dashboard", "◧  Dashboard", "/"),
       ("callsheet", "☎  Call Sheet", "/callsheet"),
       ("leads", "▤  Leads", "/leads")]

CSS = """
:root{--bg:#0b0d12;--panel:#141821;--panel2:#1b2130;--line:#262d3b;--fg:#e9edf3;
 --muted:#8c94a3;--accent:#2dd4a7;--accent2:#5b8cff;--hot:#ff5d6c;--warm:#f0a73e;--cold:#5a6678;}
*{box-sizing:border-box} html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--accent2);text-decoration:none} a:hover{text-decoration:underline}
.shell{display:flex;min-height:100vh}
.side{width:230px;background:#0e1118;border-right:1px solid var(--line);position:sticky;top:0;height:100vh;padding:22px 14px;flex-shrink:0}
.brand{font-weight:800;font-size:20px;letter-spacing:.06em;color:#fff}
.brand b{color:var(--accent)} .tag{color:var(--muted);font-size:11px;margin:2px 0 26px;line-height:1.4}
.nav a{display:block;color:var(--fg);padding:10px 12px;border-radius:10px;margin:4px 0;font-size:14px}
.nav a.active{background:var(--panel2);color:#fff;box-shadow:inset 0 0 0 1px var(--line)}
.nav a:hover{background:var(--panel);text-decoration:none}
.side .foot{position:absolute;bottom:18px;left:14px;right:14px;color:var(--muted);font-size:11px}
.main{flex:1;min-width:0;padding:26px 30px 90px}
.h1{font-size:22px;font-weight:700;margin:0 0 2px} .hsub{color:var(--muted);font-size:13px;margin-bottom:22px}
.grid{display:grid;gap:14px} .g4{grid-template-columns:repeat(4,1fr)} .g3{grid-template-columns:repeat(3,1fr)} .g2{grid-template-columns:repeat(2,1fr)}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.tile .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.tile .v{font-size:28px;font-weight:800;margin-top:6px} .tile .s{color:var(--muted);font-size:12px;margin-top:2px}
.funnel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}
.fbar{display:flex;align-items:center;gap:12px;margin:9px 0}
.fbar .lbl{width:120px;color:var(--muted);font-size:13px} .fbar .track{flex:1;background:#0e1118;border-radius:8px;height:26px;overflow:hidden}
.fbar .fill{height:100%;background:linear-gradient(90deg,var(--accent2),var(--accent));display:flex;align-items:center;padding:0 10px;color:#04140f;font-weight:700;font-size:13px;min-width:34px}
.rate{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--line)}
.badge{font-size:11px;padding:2px 9px;border-radius:20px;font-weight:700}
.ok{background:#0f3b2e;color:var(--accent)} .bad{background:#3b1620;color:var(--hot)}
.flag{background:#2a1d10;border-left:3px solid var(--warm);padding:11px 14px;border-radius:9px;margin:8px 0}
.flag b{color:var(--warm)}
.trend{display:flex;align-items:flex-end;gap:8px;height:90px;margin-top:10px}
.trend .col{flex:1;display:flex;flex-direction:column;align-items:center;gap:5px;color:var(--muted);font-size:11px}
.trend .b{width:70%;background:var(--accent2);border-radius:4px 4px 0 0;min-height:3px}
table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);font-size:13px}
th{color:var(--muted);font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.04em}
tr:hover td{background:var(--panel)}
.pill{font-size:11px;padding:2px 8px;border-radius:20px;background:var(--panel2)}
.pill.hot{background:#3b1620;color:var(--hot)} .pill.warm{background:#352814;color:var(--warm)} .pill.cold{background:#1c222e;color:var(--cold)}
.q{color:var(--accent);font-weight:700} .nq{color:var(--muted)}
.filters{display:flex;gap:8px;margin-bottom:14px} .filters a{padding:6px 12px;border:1px solid var(--line);border-radius:20px;color:var(--fg);font-size:12px}
.filters a.on{background:var(--accent);color:#04140f;border-color:var(--accent)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;margin:14px 0;overflow:hidden}
.card.active{border-color:var(--accent);box-shadow:0 0 0 2px rgba(45,212,167,.14)} .card.done{opacity:.5}
.chead{display:flex;gap:14px;padding:14px 16px;background:var(--panel2);align-items:flex-start}
.rank{font-size:20px;font-weight:800;color:var(--muted);min-width:26px}
.chead h2{margin:0;font-size:16px} .cmeta{color:var(--muted);font-size:12px;margin-top:3px}
.call{margin-left:auto;text-align:right} .tel{font-size:19px;font-weight:800;color:var(--accent)}
.warn{color:var(--warm);font-size:11px}
.cbody{padding:14px 16px} h3.s{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:12px 0 6px}
.opener{background:#0e1118;border-left:3px solid var(--accent);border-radius:7px;padding:11px 13px;font-size:15px}
.pending{color:var(--warm)} .cols{display:flex;gap:22px;flex-wrap:wrap}.cols>div{flex:1;min-width:230px}
ul.f{margin:0;padding-left:16px} ul.f li{margin:4px 0}
.sev{color:#fff;font-size:10px;padding:1px 6px;border-radius:4px;text-transform:uppercase;margin-right:5px}
.actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}
button{background:var(--panel2);color:var(--fg);border:1px solid var(--line);padding:8px 12px;border-radius:9px;cursor:pointer;font-size:13px}
button:hover{border-color:var(--accent)} button.danger{background:#3b1620} button.go{background:#162a3b} button.sold{background:#0f3b2e;font-weight:700}
.logged{color:var(--accent);align-self:center;font-weight:700;margin-left:6px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:6px 14px;font-size:13px} .kv .k{color:var(--muted)}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre-wrap;background:#0e1118;border:1px solid var(--line);border-radius:8px;padding:12px}
.back{color:var(--muted);font-size:13px}
/* ── polish ───────────────────────────────────────────────────────────── */
html{scroll-behavior:smooth} ::selection{background:rgba(45,212,167,.3)}
*:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
.tile{transition:border-color .15s,transform .15s} .tile:hover{border-color:#32445c}
.card{transition:border-color .15s,box-shadow .15s,transform .15s}
.card:hover{transform:translateY(-1px)} .brand{letter-spacing:.08em}
.copybtn{background:transparent;border:1px solid var(--line);color:var(--muted);
 font-size:11px;padding:3px 9px;border-radius:7px;cursor:pointer;margin-left:8px;vertical-align:middle}
.copybtn:hover{border-color:var(--accent);color:var(--accent)}
.row-between{display:flex;align-items:center;justify-content:space-between;gap:8px}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:var(--accent);
 color:#04140f;font-weight:700;padding:10px 18px;border-radius:30px;z-index:50;
 box-shadow:0 8px 24px rgba(0,0,0,.4);animation:pop .2s ease}
@keyframes pop{from{opacity:0;transform:translate(-50%,8px)}to{opacity:1;transform:translate(-50%,0)}}
.hint{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:6px;
 padding:1px 7px;font-size:11px;font-family:ui-monospace,Consolas,monospace;color:var(--muted)}
/* ── responsive: sidebar → top bar on phones/tablets ─────────────────────── */
@media (max-width:1100px){.g4{grid-template-columns:repeat(2,1fr)}}
@media (max-width:860px){
 .shell{flex-direction:column}
 .side{position:sticky;top:0;z-index:10;width:auto;height:auto;display:flex;align-items:center;
   gap:14px;flex-wrap:wrap;padding:12px 16px}
 .side .brand{font-size:17px} .side .tag,.side .foot{display:none}
 .nav{display:flex;gap:6px;flex:1} .nav a{margin:0;padding:8px 12px;font-size:13px}
 .main{padding:18px 16px 80px}
 .g4,.g3,.g2{grid-template-columns:1fr} .cols{flex-direction:column}
 .chead{flex-wrap:wrap} .call{margin-left:0;text-align:left;width:100%}
 .kv{grid-template-columns:120px 1fr}
}
@media (max-width:520px){.actions button{flex:1 1 44%}}
"""

SHARED_JS = """
<script>
async function logOutcome(id, outcome){
  let note='', callback='';
  if(outcome==='CALLBACK'){ callback=prompt('Callback when? (YYYY-MM-DD HH:MM)')||''; if(!callback)return; }
  if(outcome==='NOT_INTERESTED'){ if(!confirm('Add to suppression — never contact again?'))return; }
  const r=await fetch('/outcome',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({lead_id:id,status:outcome,note,callback_at:callback})});
  if(r.ok){const c=document.getElementById('card-'+id);
    if(c){c.classList.add('done');c.querySelector('.actions').insertAdjacentHTML('beforeend','<span class="logged">\\u2713 '+outcome+'</span>');}
    else location.reload();}
  else alert('Failed to log outcome.');
}
async function writeDraft(id){const r=await fetch('/write',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({lead_id:id})}); if(r.ok)location.reload(); else alert('Write failed.');}
let cur=0;const cards=()=>[...document.querySelectorAll('.card')];
function focusCard(n){const cs=cards();if(!cs.length)return;cur=Math.max(0,Math.min(cs.length-1,n));
  cs.forEach((c,i)=>c.classList.toggle('active',i===cur));cs[cur].scrollIntoView({behavior:'smooth',block:'center'});}
document.addEventListener('click',e=>{const b=e.target.closest('button[data-o]');if(!b)return;
  logOutcome(+b.closest('.card').dataset.id,b.dataset.o);});
document.addEventListener('keydown',e=>{if(/INPUT|TEXTAREA/.test(e.target.tagName))return;
  if(e.key==='j')focusCard(cur+1);else if(e.key==='k')focusCard(cur-1);
  else if('123456'.includes(e.key)){const b=cards()[cur]?.querySelectorAll('button[data-o]')[+e.key-1];b?.click();}});
if(cards().length)focusCard(0);
function toast(m){const d=document.createElement('div');d.className='toast';d.textContent=m;
  document.body.appendChild(d);setTimeout(()=>d.remove(),1400);}
function copyFrom(id){const el=document.getElementById(id);if(!el)return;
  const text=(el.innerText||el.textContent||'').trim();
  const done=()=>toast('Copied ✓');
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(text).then(done).catch(()=>fallback(text,done));}
  else fallback(text,done);}
function fallback(text,done){const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';
  ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done();}catch(e){}
  ta.remove();}
document.addEventListener('click',e=>{const b=e.target.closest('[data-copy]');if(b)copyFrom(b.dataset.copy);});
</script>"""


def page(title: str, body: str, cfg: dict, active: str = "") -> str:
    nav = "".join(
        f'<a href="{href}" class="{"active" if key==active else ""}">{html.escape(label)}</a>'
        for key, label, href in NAV)
    biz = html.escape(str(cfg.get("business_name", "")))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {BRAND}</title><style>{CSS}</style></head><body>
<div class="shell">
 <aside class="side">
   <div class="brand"><b>TD</b>SOCH</div>
   <div class="tag">{TAGLINE}</div>
   <nav class="nav">{nav}</nav>
   <div class="foot">{biz or 'configure business_name'}<br>{dt.date.today():%d %b %Y}</div>
 </aside>
 <main class="main">{body}</main>
</div>{SHARED_JS}</body></html>"""


# ── Dashboard ──────────────────────────────────────────────────────────────────
def dashboard_body(m: dict, cfg: dict) -> str:
    f = m["funnel"]
    maxv = max(f.values()) or 1
    order = [("found", "Found"), ("audited", "Audited"), ("qualified", "Qualified"),
             ("called", "Called"), ("conversations", "Conversations"),
             ("audits_sent", "Audits sent"), ("sold", "Sold")]
    bars = ""
    for key, lbl in order:
        v = f[key]; w = max(4, round(100 * v / maxv))
        bars += (f'<div class="fbar"><div class="lbl">{lbl}</div>'
                 f'<div class="track"><div class="fill" style="width:{w}%">{v}</div></div></div>')
    def rate_row(name, val, tgt):
        ok = val >= tgt
        return (f'<div class="rate"><span>{name}</span><span>'
                f'<b>{val:.0%}</b> <span class="badge {"ok" if ok else "bad"}">target {tgt:.0%}</span></span></div>')
    rates = (rate_row("Conversation rate", m["rates"]["conversation_rate"], m["targets"]["conversation_rate"])
             + rate_row("“Send me the audit”", m["rates"]["send_audit_rate"], m["targets"]["send_audit_rate"])
             + rate_row("Close rate", m["rates"]["close_rate"], m["targets"]["close_rate"]))
    tmax = max((t["count"] for t in m["trend"]), default=1) or 1
    trend = "".join(f'<div class="col"><div class="b" style="height:{round(70*t["count"]/tmax)}px"></div>'
                    f'{t["count"]}<span>{t["day"]}</span></div>' for t in m["trend"])
    flags = "".join(f'<div class="flag"><b>⚑ {html.escape(t)}</b> — {html.escape(msg)}</div>'
                    for t, msg in m["flags"]) or '<div class="tile">All tracked steps at or above target. 🎯</div>'
    pkr = f'₨{m["revenue_pkr"]:,.0f}' if m["pkr_rate"] else '(set aud_to_pkr in config)'
    return f"""
<div class="h1">Dashboard</div><div class="hsub">Funnel health & conversion vs targets</div>
<div class="grid g4">
  <div class="tile"><div class="k">Qualified</div><div class="v">{f['qualified']}</div><div class="s">of {f['found']} found</div></div>
  <div class="tile"><div class="k">Called</div><div class="v">{f['called']}</div><div class="s">{f['conversations']} conversations</div></div>
  <div class="tile"><div class="k">Sold</div><div class="v">{f['sold']}</div><div class="s">{f['audits_sent']} audits sent</div></div>
  <div class="tile"><div class="k">Revenue</div><div class="v">A${m['revenue_aud']:,.0f}</div><div class="s">{pkr}</div></div>
</div>
<div class="grid g2" style="margin-top:14px">
  <div class="funnel"><h3 class="s">Funnel</h3>{bars}</div>
  <div>
    <div class="tile"><h3 class="s">Conversion vs target</h3>{rates}</div>
    <div class="tile" style="margin-top:14px"><h3 class="s">Leads found — last 7 days</h3><div class="trend">{trend}</div></div>
  </div>
</div>
<h3 class="s" style="margin-top:20px">Red flags</h3>{flags}
"""


# ── Call sheet ──────────────────────────────────────────────────────────────────
def _card(c: dict, i: int) -> str:
    sev_color = {"high": "#ff5d6c", "medium": "#f0a73e", "low": "#5a6678"}
    findings = "".join(
        f'<li><span class="sev" style="background:{sev_color.get(f["severity"],"#5a6678")}">{f["severity"]}</span>'
        f'{html.escape(f["detail"])}</li>' for f in c["findings"])
    obj = "".join(f'<li><b>“{html.escape(o)}”</b> → {html.escape(a)}</li>' for o, a in c["objections"])
    opener = (f'{html.escape(c["opener"])}' if c["opener"]
              else '<span class="pending">Opener pending — <a href="#" onclick="writeDraft('
                    + str(c["id"]) + ');return false">write now</a> (Step 3).</span>')
    phone = html.escape(c["phone"] or "")
    tel = f'<a class="tel" href="tel:{phone}">{phone}</a>' if phone else '<span class="warn">no phone</span>'
    mob = ' <span class="warn">⚠ mobile</span>' if c["phone_type"] == "mobile" else ""
    dne = ' <span class="warn">✉ do-not-email</span>' if c["do_not_email"] else ""
    email = f'<div style="color:var(--muted);font-size:12px">{html.escape(c["email"])}</div>' if c["email"] else ""
    last = f'<div style="color:var(--muted);font-size:12px;margin-top:8px">last: {html.escape(c["last_outcome"])}</div>' if c["last_outcome"] else ""
    return f"""
<div class="card" id="card-{c['id']}" data-id="{c['id']}">
  <div class="chead"><div class="rank">{i}</div>
    <div><h2><a href="/lead/{c['id']}">{html.escape(c['name'])}</a>
      <span class="pill {c['tier']}">{c['score']}/100 · {c['tier']}</span></h2>
      <div class="cmeta">{html.escape(c['city'])} · <b>{c['local_time']}</b> · {html.escape(c['niche'])}
        · <a href="{html.escape(c['website'])}" target="_blank" rel="noopener">{html.escape(c['domain'])}</a></div></div>
    <div class="call">{tel}{mob}{dne}{email}</div></div>
  <div class="cbody">
    <div class="row-between"><h3 class="s">Opener</h3>
      <button class="copybtn" data-copy="op-{c['id']}">copy</button></div>
    <div class="opener" id="op-{c['id']}">{opener}</div>
    <div class="cols"><div><h3 class="s">Top findings</h3><ul class="f">{findings or '<li>—</li>'}</ul></div>
      <div><h3 class="s">Objections</h3><ul class="f">{obj or '<li>—</li>'}</ul></div></div>
    {last}
    <div class="actions">
      <button data-o="NO_ANSWER">No answer (1)</button>
      <button data-o="GATEKEEPER">Gatekeeper (2)</button>
      <button data-o="NOT_INTERESTED" class="danger">Not interested (3)</button>
      <button data-o="SEND_AUDIT" class="go">Send audit (4)</button>
      <button data-o="CALLBACK">Callback… (5)</button>
      <button data-o="SOLD" class="sold">SOLD 🎉 (6)</button>
    </div>
  </div></div>"""


def callsheet_body(cards: list[dict]) -> str:
    rows = "".join(_card(c, i) for i, c in enumerate(cards, 1))
    empty = '<div class="tile">No qualified leads yet. Run <span class="mono">python tdsoch.py run</span>.</div>'
    return (f'<div class="h1">Call Sheet</div>'
            f'<div class="hsub">{len(cards)} qualified · best first &nbsp; '
            f'<span class="hint">j</span><span class="hint">k</span> move &nbsp; '
            f'<span class="hint">1</span>–<span class="hint">6</span> log outcome</div>{rows or empty}')


# ── Leads table ──────────────────────────────────────────────────────────────────
def leads_body(conn, flt: str) -> str:
    where = {"qualified": "WHERE s.qualified=1", "all": ""}.get(flt, "WHERE s.qualified=1")
    rows = conn.execute(f"""
        SELECT l.id,l.name,l.root_domain,l.city,l.niche,l.phone,l.phone_type,l.status,
               s.score,s.qualified,s.tier,s.top_problem,
               (SELECT status FROM outcomes o WHERE o.lead_id=l.id ORDER BY id DESC LIMIT 1) last
        FROM leads l LEFT JOIN scores s ON s.lead_id=l.id {where}
        ORDER BY s.qualified DESC, s.score DESC, l.id""").fetchall()
    trs = ""
    for r in rows:
        q = '<span class="q">✓</span>' if r["qualified"] else '<span class="nq">—</span>'
        tier = f'<span class="pill {r["tier"] or "cold"}">{r["tier"] or "-"}</span>'
        trs += (f'<tr onclick="location=\'/lead/{r["id"]}\'" style="cursor:pointer">'
                f'<td><b>{html.escape(r["name"] or r["root_domain"])}</b><br>'
                f'<span style="color:var(--muted);font-size:11px">{html.escape(r["root_domain"])}</span></td>'
                f'<td>{html.escape(r["city"] or "")}</td><td>{html.escape(r["niche"] or "")}</td>'
                f'<td>{r["score"] if r["score"] is not None else "-"}</td><td>{q}</td><td>{tier}</td>'
                f'<td>{html.escape(r["phone"] or "—")}</td>'
                f'<td>{html.escape(r["last"] or r["status"] or "")}</td></tr>')
    f_all = "on" if flt == "all" else ""
    f_q = "on" if flt != "all" else ""
    return f"""<div class="h1">Leads</div><div class="hsub">{len(rows)} shown</div>
<div class="filters"><a href="/leads?f=qualified" class="{f_q}">Qualified</a><a href="/leads?f=all" class="{f_all}">All</a></div>
<table><tr><th>Business</th><th>City</th><th>Niche</th><th>Score</th><th>Qual</th><th>Tier</th><th>Phone</th><th>Last</th></tr>
{trs or '<tr><td colspan=8 style="color:var(--muted)">No leads yet.</td></tr>'}</table>"""


# ── Lead detail ──────────────────────────────────────────────────────────────────
def lead_detail_body(conn, lead_id: int) -> str:
    lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not lead:
        return '<div class="h1">Not found</div><a class="back" href="/leads">← leads</a>'
    lead = dict(lead)
    a = db.audit_for(conn, lead_id); a = dict(a) if a else {}
    sc = conn.execute("SELECT * FROM scores WHERE lead_id=?", (lead_id,)).fetchone()
    dr = conn.execute("SELECT * FROM drafts WHERE lead_id=?", (lead_id,)).fetchone()
    findings = json.loads(a.get("findings_json") or "[]")
    sev_color = {"high": "#ff5d6c", "medium": "#f0a73e", "low": "#5a6678"}
    fhtml = "".join(f'<li><span class="sev" style="background:{sev_color.get(f["severity"],"#5a6678")}">'
                    f'{f["severity"]}</span>{html.escape(f["detail"])}</li>' for f in findings) or "<li>—</li>"
    outcomes = conn.execute("SELECT status,note,created_at FROM outcomes WHERE lead_id=? ORDER BY id DESC", (lead_id,)).fetchall()
    ohtml = "".join(f'<div class="rate"><span>{html.escape(o["status"])} '
                    f'<span style="color:var(--muted)">{html.escape(o["note"] or "")}</span></span>'
                    f'<span style="color:var(--muted)">{o["created_at"][:16]}</span></div>' for o in outcomes) or '<div style="color:var(--muted)">no calls logged</div>'
    draft_html = ""
    if dr and dr["opener"]:
        dm_txt = dr["dm"] if ("dm" in dr.keys() and dr["dm"]) else ""
        email_txt = (dr["email_subject"] or "") + chr(10) + chr(10) + (dr["email_body"] or "")
        def hdr(title, cid):
            return (f'<div class="row-between"><h3 class="s">{title}</h3>'
                    f'<button class="copybtn" data-copy="{cid}">copy</button></div>')
        dm_block = (hdr("Cold DM (IG / FB / LinkedIn)", "d-dm")
                    + f'<div class="mono" id="d-dm">{html.escape(dm_txt)}</div>') if dm_txt else ""
        draft_html = (
            '<div class="tile">'
            + hdr("Call opener", "d-op") + f'<div class="opener" id="d-op">{html.escape(dr["opener"])}</div>'
            + hdr("Email draft", "d-em") + f'<div class="mono" id="d-em">{html.escape(email_txt)}</div>'
            + dm_block
            + (f'<div style="margin-top:10px"><a href="/audit/{html.escape(lead["root_domain"])}" target="_blank">open one-page audit →</a></div>' if dr["pdf_path"] else "")
            + '</div>')
    else:
        draft_html = (f'<div class="tile">No draft yet. '
                      f'<button onclick="writeDraft({lead_id})" class="go">Write opener + email</button></div>')
    kv = lambda k, v: f'<div class="k">{k}</div><div>{html.escape(str(v))}</div>'
    q = "✓ qualified" if sc and sc["qualified"] else "not qualified"
    return f"""<a class="back" href="/leads">← leads</a>
<div class="h1" style="margin-top:8px">{html.escape(lead['name'] or lead['root_domain'])}
  <span class="pill {sc['tier'] if sc else 'cold'}">{(str(sc['score'])+'/100') if sc else '-'} · {q}</span></div>
<div class="hsub"><a href="{html.escape(lead['website'])}" target="_blank">{html.escape(lead['website'])}</a></div>
<div class="grid g2">
 <div class="tile"><h3 class="s">Lead</h3><div class="kv">
   {kv('City / niche', (lead['city'] or '')+' · '+(lead['niche'] or ''))}
   {kv('Phone', (lead['phone'] or '—')+' ('+(lead['phone_type'] or '')+')')}
   {kv('Email(s)', a.get('emails_found') or lead.get('email') or '—')}
   {kv('Address', lead.get('address') or '—')}
   {kv('Source / ABN', (lead.get('source') or '')+' · '+(lead.get('abn_status') or ''))}
 </div>
 <h3 class="s">Audit signals</h3><div class="kv">
   {kv('HTTP / HTTPS', str(a.get('http_status'))+' / '+('yes' if a.get('https_ok') else 'no'))}
   {kv('WordPress', ('yes '+(a.get('wp_version') or '')) if a.get('is_wordpress') else 'no')}
   {kv('Mobile viewport', 'yes' if a.get('has_viewport') else 'NO')}
   {kv('PageSpeed (mobile)', a.get('psi_perf') if a.get('psi_perf') is not None else '— (run --psi)')}
   {kv('Pages / booking / ads', str(a.get('internal_links'))+' · '+('✓' if a.get('has_booking') else '–')+' · '+('✓' if a.get('has_ads_tag') else '–'))}
   {kv('Footer year', a.get('footer_year') or '—')}
 </div></div>
 <div><div class="tile"><h3 class="s">Findings</h3><ul class="f">{fhtml}</ul></div>
   <div class="tile" style="margin-top:14px"><h3 class="s">Call history</h3>{ohtml}</div></div>
</div>
<div style="margin-top:14px">{draft_html}</div>"""
