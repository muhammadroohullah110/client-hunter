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

# Inline SVG icons (stroke, 18px) — no emoji, theme-aware via currentColor.
_IC = {
    "dashboard": '<path d="M3 3h7v7H3zM14 3h7v4h-7zM14 10h7v11h-7zM3 13h7v8H3z"/>',
    "callsheet": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.6A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.9a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.2-1.2a2 2 0 0 1 2.1-.5c.9.3 1.9.6 2.9.7a2 2 0 0 1 1.7 2z"/>',
    "leads": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
}


def _icon(name: str) -> str:
    return (f'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{_IC.get(name, "")}</svg>')


NAV = [("dashboard", "Dashboard", "/"),
       ("callsheet", "Call Sheet", "/callsheet"),
       ("leads", "Leads", "/leads"),
       ("settings", "Settings", "/settings")]

CSS = """
:root{--bg:#0a0d14;--panel:#121722;--panel2:#1a2130;--line:#232c3d;--fg:#eaf0f8;
 --muted:#8893a6;--accent:#10b981;--accent-strong:#059669;--accent2:#3b82f6;--accent2-strong:#2563eb;
 --hot:#f87171;--warm:#fbbf24;--cold:#64748b;--mono:'Fira Code',ui-monospace,Consolas,monospace;}
*{box-sizing:border-box} html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--fg);
 font:14px/1.55 'Fira Sans',system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
/* tabular numbers for all data/metrics */
.tile .v,.score,.fbar .fill,.rate b,.hint,td,.pill{font-variant-numeric:tabular-nums}
a{color:var(--accent2);text-decoration:none} a:hover{text-decoration:underline}
.shell{display:flex;min-height:100vh}
.side{width:230px;background:#0e1118;border-right:1px solid var(--line);position:sticky;top:0;height:100vh;padding:22px 14px;flex-shrink:0}
.brand{font-weight:800;font-size:20px;letter-spacing:.06em;color:#fff}
.brand b{color:var(--accent)} .tag{color:var(--muted);font-size:11px;margin:2px 0 26px;line-height:1.4}
.nav a{display:flex;align-items:center;gap:10px;color:var(--muted);padding:10px 12px;
 border-radius:10px;margin:3px 0;font-size:14px;font-weight:500;transition:background .15s,color .15s}
.nav a .ic{display:inline-flex;opacity:.85}
.nav a.active{background:linear-gradient(90deg,rgba(59,130,246,.16),transparent);color:#fff;
 box-shadow:inset 2px 0 0 var(--accent2)}
.nav a.active .ic{color:var(--accent2);opacity:1}
.nav a:hover{background:var(--panel);color:var(--fg);text-decoration:none}
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
.mono{font-family:var(--mono);font-size:12.5px;white-space:pre-wrap;background:#0b0f17;border:1px solid var(--line);border-radius:8px;padding:12px;line-height:1.5}
.back{color:var(--muted);font-size:13px;display:inline-flex;align-items:center;gap:5px}
.back:hover{color:var(--accent2)}
/* ── controls: inputs, selects, filter chips, action buttons ─────────────── */
input,select,textarea{background:#0b0f17;border:1px solid var(--line);color:var(--fg);
 border-radius:9px;padding:9px 11px;font:14px 'Fira Sans',system-ui,sans-serif;width:100%}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent2);
 box-shadow:0 0 0 3px rgba(59,130,246,.18)}
label.fld{display:block;margin:12px 0} label.fld .lbl{display:block;color:var(--muted);
 font-size:12px;margin-bottom:5px} label.fld .help{color:var(--muted);font-size:11px;margin-top:4px}
.btn{display:inline-flex;align-items:center;gap:6px;background:var(--accent2);color:#fff;border:none;
 padding:10px 16px;border-radius:9px;cursor:pointer;font:600 13px 'Fira Sans',sans-serif;transition:filter .15s}
.btn:hover{filter:brightness(1.1)} .btn.green{background:var(--accent)} .btn.green:hover{filter:brightness(1.08)}
.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--fg)}
.btn.ghost:hover{border-color:var(--accent2)} .btn.danger{background:#7f1d2b}
.btn.sm{padding:7px 12px;font-size:12px}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 16px}
.toolbar input[type=search]{max-width:260px}
.toolbar select{width:auto;min-width:130px}
.savebar{position:sticky;bottom:0;background:linear-gradient(180deg,transparent,var(--bg) 40%);
 padding:16px 0 4px;margin-top:8px;display:flex;gap:10px;align-items:center}
.ok-dot{color:var(--accent)} .lead-actions{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
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
async function leadAction(id,action,btn){
  if(action==='suppress'&&!confirm('Suppress this lead — never contact again?'))return;
  if(btn){btn.disabled=true;btn.textContent=(action==='reaudit'?'Re-auditing…':'Working…');}
  const r=await fetch('/lead-action',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({lead_id:id,action})});
  if(r.ok){toast(action==='reaudit'?'Re-audited ✓':'Done ✓');setTimeout(()=>location.reload(),500);}
  else{toast('Failed');if(btn)btn.disabled=false;}}
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
        f'<a href="{href}" class="{"active" if key==active else ""}">'
        f'<span class="ic">{_icon(key)}</span>{html.escape(label)}</a>'
        for key, label, href in NAV)
    biz = html.escape(str(cfg.get("business_name", "")))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {BRAND}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
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
def settings_body(cfg: dict) -> str:
    q = cfg.get("qualify", {}); gates = q.get("gates", {}); offer = cfg.get("offer", {})
    dash = cfg.get("dashboard", {})
    def fld(key, label, val, help="", typ="text"):
        v = "" if val is None else html.escape(str(val))
        return (f'<label class="fld"><span class="lbl">{html.escape(label)}</span>'
                f'<input type="{typ}" data-k="{key}" value="{v}">'
                + (f'<span class="help">{html.escape(help)}</span>' if help else "") + '</label>')
    def area(key, label, items, help=""):
        v = html.escape("\n".join(items or []))
        return (f'<label class="fld"><span class="lbl">{html.escape(label)}</span>'
                f'<textarea data-k="{key}" rows="4">{v}</textarea>'
                + (f'<span class="help">{html.escape(help)}</span>' if help else "") + '</label>')
    def toggle(key, label, on):
        return (f'<label class="fld" style="display:flex;align-items:center;gap:10px;margin:8px 0">'
                f'<input type="checkbox" data-k="{key}" {"checked" if on else ""} style="width:auto">'
                f'<span class="lbl" style="margin:0">{html.escape(label)}</span></label>')
    return f"""<div class="h1">Settings</div><div class="hsub">Edit everything the engine uses — saved to config.yaml</div>
<div class="grid g2">
 <div class="tile"><h3 class="s">Business</h3>
   {fld('business_name','Business name',cfg.get('business_name'))}
   {fld('my_name','Your name',cfg.get('my_name'))}
   {fld('my_email','Your email',cfg.get('my_email'),'Used in the crawler User-Agent')}
   {fld('my_phone','Your AU phone / VoIP',cfg.get('my_phone'))}
   {fld('payment_link','Payment link',cfg.get('payment_link'),'Payoneer / Wise request link')}
 </div>
 <div class="tile"><h3 class="s">Offer</h3>
   {fld('offer.name','Offer name',offer.get('name'))}
   {fld('offer.price_aud','Price (A$)',offer.get('price_aud'),'',"number")}
   {fld('offer.delivery_hours','Delivery (hours)',offer.get('delivery_hours'),'',"number")}
   {fld('offer.upsell_monthly_aud','Care plan /mo (A$)',offer.get('upsell_monthly_aud'),'',"number")}
   {fld('dashboard.aud_to_pkr','A$ → ₨ rate',dash.get('aud_to_pkr'),'For the revenue tile',"number")}
 </div>
 <div class="tile"><h3 class="s">Targeting</h3>
   {area('cities','Cities (one per line)',cfg.get('cities'),'AU cities to hunt')}
   {area('niches','Niches (one per line)',cfg.get('niches'),'dentist, physiotherapist, accountant, plumber, electrician')}
   {fld('daily_new_leads_target','Find per night',cfg.get('daily_new_leads_target'),'',"number")}
   {fld('daily_claude_leads_cap','Max written per day',cfg.get('daily_claude_leads_cap'),'',"number")}
 </div>
 <div class="tile"><h3 class="s">Qualifier — thresholds</h3>
   {fld('qualify.min_pages_for_pay_signal','Min pages = ability-to-pay',q.get('min_pages_for_pay_signal'),'',"number")}
   {fld('qualify.psi_fail_threshold','PageSpeed fail below',q.get('psi_fail_threshold'),'mobile score 0–100',"number")}
   {fld('qualify.lcp_fail_seconds','LCP slow above (sec)',q.get('lcp_fail_seconds'),'',"number")}
   {fld('qualify.copyright_stale_years','Stale footer after (yrs)',q.get('copyright_stale_years'),'',"number")}
   <h3 class="s" style="margin-top:14px">Hard gates (a lead must clear all enabled)</h3>
   {toggle('qualify.gates.require_reachable','Reachable',gates.get('require_reachable',True))}
   {toggle('qualify.gates.require_not_chain','Not a chain',gates.get('require_not_chain',True))}
   {toggle('qualify.gates.require_fixable_problem','Has a fixable problem',gates.get('require_fixable_problem',True))}
   {toggle('qualify.gates.require_ability_to_pay','Can pay',gates.get('require_ability_to_pay',True))}
 </div>
</div>
<div class="savebar"><button class="btn green" onclick="saveSettings()">Save settings</button>
 <span class="help">Changes apply to the next run / page refresh.</span></div>
<script>
async function saveSettings(){{const data={{}};
  document.querySelectorAll('[data-k]').forEach(el=>{{
    let v = el.type==='checkbox'?el.checked:(el.tagName==='TEXTAREA'?el.value.split(/\\n+/).map(s=>s.trim()).filter(Boolean):el.value);
    data[el.dataset.k]=v;}});
  const r=await fetch('/settings',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
  if(r.ok)toast('Settings saved ✓');else toast('Save failed');}}
</script>"""


def leads_body(conn, flt: str, params: dict | None = None) -> str:
    p = params or {}
    niche_f = p.get("niche", ""); city_f = p.get("city", ""); q_f = (p.get("q", "") or "").strip()
    sort = p.get("sort", "score")
    where, args = [], []
    if flt == "qualified":
        where.append("s.qualified=1")
    elif flt == "unqualified":
        where.append("(s.qualified=0 OR s.qualified IS NULL)")
    if niche_f:
        where.append("l.niche=?"); args.append(niche_f)
    if city_f:
        where.append("l.city=?"); args.append(city_f)
    if q_f:
        where.append("(l.name LIKE ? OR l.root_domain LIKE ?)"); args += [f"%{q_f}%", f"%{q_f}%"]
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    order = {"score": "s.score DESC", "name": "l.name", "city": "l.city, l.niche",
             "niche": "l.niche, s.score DESC"}.get(sort, "s.score DESC")
    rows = conn.execute(f"""
        SELECT l.id,l.name,l.root_domain,l.city,l.niche,l.phone,l.phone_type,l.status,
               s.score,s.qualified,s.tier,s.top_problem,
               (SELECT status FROM outcomes o WHERE o.lead_id=l.id ORDER BY id DESC LIMIT 1) last
        FROM leads l LEFT JOIN scores s ON s.lead_id=l.id {wsql}
        ORDER BY s.qualified DESC, {order}, l.id""", args).fetchall()
    niches = [r[0] for r in conn.execute("SELECT DISTINCT niche FROM leads WHERE niche<>'' ORDER BY niche")]
    cities = [r[0] for r in conn.execute("SELECT DISTINCT city FROM leads WHERE city<>'' ORDER BY city")]

    def opt(val, cur, label=None):
        return f'<option value="{html.escape(val)}" {"selected" if val==cur else ""}>{html.escape(label or val or "All")}</option>'
    def sel(name, cur, vals, alllabel):
        os_ = opt("", cur, alllabel) + "".join(opt(v, cur) for v in vals)
        return f'<select name="{name}" onchange="this.form.submit()">{os_}</select>'
    flt_sel = ('<select name="f" onchange="this.form.submit()">'
               + "".join(opt(v, flt, l) for v, l in [("qualified", "Qualified"), ("unqualified", "Not qualified"), ("all", "All leads")])
               + '</select>')
    sort_sel = ('<select name="sort" onchange="this.form.submit()">'
                + "".join(opt(v, sort, "Sort: " + l) for v, l in [("score", "Score"), ("name", "Name"), ("city", "City"), ("niche", "Niche")])
                + '</select>')
    toolbar = (f'<form class="toolbar" method="get" action="/leads">'
               f'<input type="search" name="q" placeholder="Search business or domain…" value="{html.escape(q_f)}">'
               f'{flt_sel}{sel("niche", niche_f, niches, "All niches")}{sel("city", city_f, cities, "All cities")}{sort_sel}'
               f'<button class="btn ghost sm" type="submit">Apply</button></form>')

    trs = ""
    for r in rows:
        qd = '<span class="q">✓</span>' if r["qualified"] else '<span class="nq">—</span>'
        tier = f'<span class="pill {r["tier"] or "cold"}">{r["tier"] or "-"}</span>'
        trs += (f'<tr onclick="location=\'/lead/{r["id"]}\'" style="cursor:pointer">'
                f'<td><b>{html.escape(r["name"] or r["root_domain"])}</b><br>'
                f'<span style="color:var(--muted);font-size:11px">{html.escape(r["root_domain"])}</span></td>'
                f'<td>{html.escape(r["city"] or "")}</td><td>{html.escape(r["niche"] or "")}</td>'
                f'<td>{r["score"] if r["score"] is not None else "-"}</td><td>{qd}</td><td>{tier}</td>'
                f'<td>{html.escape(r["phone"] or "—")}</td>'
                f'<td>{html.escape(r["last"] or r["status"] or "")}</td></tr>')
    return f"""<div class="h1">Leads</div><div class="hsub">{len(rows)} shown</div>
{toolbar}
<table><tr><th>Business</th><th>City</th><th>Niche</th><th>Score</th><th>Qual</th><th>Tier</th><th>Phone</th><th>Last</th></tr>
{trs or '<tr><td colspan=8 style="color:var(--muted);padding:20px">No leads match. Try clearing filters or run <span class="mono">python tdsoch.py run</span>.</td></tr>'}</table>"""


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
<div class="lead-actions">
  <button class="btn green sm" onclick="writeDraft({lead_id})">{'Re-write' if dr else 'Write'} opener + email + DM</button>
  <button class="btn ghost sm" onclick="leadAction({lead_id},'reaudit',this)">Re-audit now</button>
  <button class="btn danger sm" onclick="leadAction({lead_id},'suppress',this)">Suppress (never contact)</button>
</div>
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
