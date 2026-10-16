"""
webapp.py — TDSOCH's single local web app. One beautiful UI over the whole
pipeline: Dashboard, Call Sheet, Leads, and per-lead detail — with one-click
outcome logging and on-demand opener/email writing. Stdlib server, no Flask.

    python -m engine.webapp              # http://localhost:8700
    python -m engine.webapp --port 9000

Nothing is auto-dialled or auto-sent. You call, you click, you send.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import db, webui, write
from .callsheet import build_cards, record_outcome
from .common import AUDIT_DIR, OUT_DIR, get_logger, load_config
from .dashboard import metrics

log = get_logger("web")

# Shared state for the Run page (one pipeline at a time).
RUN_STATE: dict = {"running": False, "log": []}
_RUN_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    cfg: dict = {}
    limit: int = 25

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/":
                return self._send(200, webui.page("Dashboard", webui.dashboard_body(metrics(), self.cfg),
                                                  self.cfg, active="dashboard"))
            if path == "/callsheet":
                with db.connect() as conn:
                    cards = build_cards(conn, self.cfg, self.limit)
                return self._send(200, webui.page("Call Sheet", webui.callsheet_body(cards),
                                                  self.cfg, active="callsheet"))
            if path == "/leads":
                flt = qs.get("f", ["qualified"])[0]
                params = {k: v[0] for k, v in qs.items()}
                with db.connect() as conn:
                    body = webui.leads_body(conn, flt, params)
                return self._send(200, webui.page("Leads", body, self.cfg, active="leads"))
            if path == "/settings":
                return self._send(200, webui.page("Settings", webui.settings_body(self.cfg),
                                                  self.cfg, active="settings"))
            if path == "/run":
                return self._send(200, webui.page("Run", webui.run_body(self.cfg), self.cfg, active="run"))
            if path == "/emails":
                with db.connect() as conn:
                    body = webui.emails_body(conn, self.cfg)
                return self._send(200, webui.page("Emails", body, self.cfg, active="emails"))
            if path == "/run-status":
                return self._send(200, json.dumps(RUN_STATE), "application/json")
            if path.startswith("/report/"):
                return self._serve_report(urllib.parse.unquote(path[len("/report/"):]))
            if path.startswith("/lead/"):
                lead_id = int(path.rsplit("/", 1)[1])
                with db.connect() as conn:
                    body = webui.lead_detail_body(conn, lead_id)
                return self._send(200, webui.page("Lead", body, self.cfg, active="leads"))
            if path.startswith("/audit/"):
                return self._serve_audit(path.rsplit("/", 1)[1])
            if path.startswith("/shot/"):
                return self._serve_file(AUDIT_DIR / urllib.parse.unquote(path[len("/shot/"):]), "image/png")
            return self._send(404, "not found", "text/plain")
        except Exception as e:
            log.error("GET %s failed: %s", path, e)
            return self._send(500, f"error: {e}", "text/plain")

    def _serve_audit(self, domain: str):
        with db.connect() as conn:
            row = conn.execute("SELECT pdf_path FROM drafts d JOIN leads l ON l.id=d.lead_id "
                               "WHERE l.root_domain=?", (domain,)).fetchone()
        if row and row["pdf_path"] and Path(row["pdf_path"]).exists():
            return self._serve_file(Path(row["pdf_path"]), "text/html; charset=utf-8")
        return self._send(404, "audit not generated yet", "text/plain")

    def _serve_file(self, p: Path, ctype: str):
        try:
            return self._send(200, p.read_bytes(), ctype)
        except Exception:
            return self._send(404, "not found", "text/plain")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send(400, '{"ok":false}', "application/json")
        try:
            if self.path == "/outcome":
                res = record_outcome(int(payload["lead_id"]), str(payload["status"]),
                                     payload.get("note", ""), payload.get("callback_at", ""))
                log.info("logged %s for lead %s", payload["status"], payload["lead_id"])
                return self._send(200, json.dumps(res), "application/json")
            if self.path == "/write":
                lid = int(payload["lead_id"])
                out_day = OUT_DIR / dt.date.today().isoformat()
                with db.connect() as conn:
                    res = write.write_one(conn, lid, self.cfg, out_day, dry_run=False)
                log.info("wrote draft for lead %s", lid)
                return self._send(200, json.dumps({"ok": bool(res)}), "application/json")
            if self.path == "/settings":
                from .common import save_config
                Handler.cfg = save_config(payload)   # persist + refresh running config
                log.info("settings saved (%d fields)", len(payload))
                return self._send(200, json.dumps({"ok": True}), "application/json")
            if self.path == "/lead-action":
                return self._lead_action(int(payload["lead_id"]), str(payload["action"]))
            if self.path == "/ai-test":
                from . import ai
                return self._send(200, json.dumps(ai.test_key(self.cfg)), "application/json")
            if self.path == "/run-pipeline":
                return self._start_pipeline(payload)
            if self.path == "/write-all":
                n = write.run()
                return self._send(200, json.dumps({"ok": True, "count": n}), "application/json")
            if self.path == "/prepare-emails":
                from . import followup
                n = followup.make_drafts()
                return self._send(200, json.dumps({"ok": True, "count": n}), "application/json")
            if self.path == "/mark-sent":
                with db.connect() as conn:
                    conn.execute("UPDATE drafts SET state='sent' WHERE lead_id=?", (int(payload["lead_id"]),))
                return self._send(200, '{"ok":true}', "application/json")
            if self.path == "/report":
                return self._gen_report(int(payload["lead_id"]))
            return self._send(404, '{"ok":false}', "application/json")
        except Exception as e:
            log.error("POST %s failed: %s", self.path, e)
            return self._send(400, json.dumps({"ok": False, "error": str(e)}), "application/json")


    def _serve_report(self, name: str):
        # Reports live under out/<date>/reports/. Search newest-first across all
        # date folders so a link still works the day after it was generated.
        base = Path(name).name  # strip any path parts
        matches = sorted(OUT_DIR.glob(f"*/reports/{base}"), reverse=True)
        if not matches and not base.endswith((".pdf", ".html")):
            matches = (sorted(OUT_DIR.glob(f"*/reports/{base}.pdf"), reverse=True)
                       or sorted(OUT_DIR.glob(f"*/reports/{base}.html"), reverse=True))
        if matches:
            p = matches[0]
            ct = "application/pdf" if p.suffix == ".pdf" else "text/html; charset=utf-8"
            return self._serve_file(p, ct)
        return self._send(404, "report not generated yet", "text/plain")

    def _gen_report(self, lead_id: int):
        from . import report
        try:
            with db.connect() as conn:
                row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
            if not row:
                return self._send(404, '{"ok":false,"error":"lead not found"}', "application/json")
            res = report.generate(dict(row), self.cfg)
            domain = dict(row)["root_domain"]
            safe = urllib.parse.quote(domain)
            url = f"/report/{safe}.pdf" if res.get("pdf_path") else f"/report/{safe}.html"
            return self._send(200, json.dumps({"ok": True, "grade": res["grade"],
                                               "overall": res["overall"], "url": url}), "application/json")
        except Exception as e:
            log.error("report failed: %s", e)
            return self._send(400, json.dumps({"ok": False, "error": str(e)}), "application/json")

    def _start_pipeline(self, payload: dict):
        with _RUN_LOCK:
            if RUN_STATE["running"]:
                return self._send(409, json.dumps({"ok": False, "error": "already running"}), "application/json")
            RUN_STATE["running"] = True
            RUN_STATE["log"] = ["Starting…"]
        cfg = self.cfg
        cities = payload.get("cities") or None
        niches = payload.get("niches") or None
        limit = payload.get("limit")
        limit = int(limit) if (limit not in (None, "", "null")) else None
        do_psi = bool(payload.get("psi"))

        def worker():
            from . import audit as audit_mod, find as find_mod, score as score_mod

            def logln(msg):
                RUN_STATE["log"].append(msg)
                RUN_STATE["log"] = RUN_STATE["log"][-40:]
                log.info("[run] %s", msg)
            try:
                logln(f"Finding leads — cities={cities or cfg.get('cities')} niches={niches or cfg.get('niches')}")
                n = find_mod.find(cities=cities, niches=niches, limit=limit)
                logln(f"Found {n} new leads. Auditing…")
                done = audit_mod.run(do_screenshot=False, do_psi=do_psi)
                logln(f"Audited {done}. Scoring…")
                score_mod.run()
                with db.connect() as conn:
                    c = db.counts(conn)
                logln(f"Done ✓  qualified {c['qualified']} of {c['leads']} total. See Leads / Call Sheet.")
            except Exception as e:
                logln(f"Error: {e}")
            finally:
                RUN_STATE["running"] = False

        threading.Thread(target=worker, daemon=True).start()
        return self._send(200, '{"ok":true}', "application/json")

    def _lead_action(self, lead_id: int, action: str):
        from . import audit as audit_mod, score as score_mod
        from .callsheet import append_suppression
        from .common import PoliteFetcher, load_exclude_domains
        try:
            with db.connect() as conn:
                lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
                if not lead:
                    return self._send(404, '{"ok":false}', "application/json")
                lead = dict(lead)
                if action == "suppress":
                    append_suppression(lead["root_domain"], lead["phone"] or "", "suppressed from web app")
                    conn.execute("DELETE FROM scores WHERE lead_id=?", (lead_id,))
                    db.set_lead_status(conn, lead_id, "suppressed")
                    log.info("suppressed lead %s", lead["root_domain"])
                    return self._send(200, '{"ok":true}', "application/json")
            if action == "reaudit":
                crawl = self.cfg.get("crawl", {})
                fetcher = PoliteFetcher(rps=crawl.get("requests_per_second_per_domain", 1),
                                        timeout=crawl.get("timeout_seconds", 15))
                a = audit_mod.audit_one(fetcher, lead, self.cfg, do_screenshot=False,
                                        do_psi=bool(crawl.get("pagespeed", False)))
                with db.connect() as conn:
                    db.save_audit(conn, lead_id, a)
                    audit_row = dict(db.audit_for(conn, lead_id))
                    result = score_mod.score_lead(lead, audit_row, self.cfg, load_exclude_domains())
                    db.save_score(conn, lead_id, result)
                    db.set_lead_status(conn, lead_id, "scored")
                log.info("re-audited lead %s (%d findings)", lead["root_domain"],
                         len(json.loads(a["findings_json"])))
                return self._send(200, '{"ok":true}', "application/json")
            return self._send(400, '{"ok":false,"error":"unknown action"}', "application/json")
        except Exception as e:
            log.error("lead-action %s failed: %s", action, e)
            return self._send(400, json.dumps({"ok": False, "error": str(e)}), "application/json")


def serve(port: int, limit: int, open_browser: bool = True) -> None:
    db.init_db()
    Handler.cfg = load_config()
    Handler.limit = limit
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    log.info("%s live at %s  (Ctrl+C to stop)", webui.BRAND, url)
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
    ap = argparse.ArgumentParser(description="TDSOCH web app.")
    ap.add_argument("--port", type=int, default=8700)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-open", dest="open", action="store_false")
    a = ap.parse_args()
    cfg = load_config()
    serve(a.port, a.limit or cfg.get("daily_claude_leads_cap", 25), open_browser=a.open)


if __name__ == "__main__":
    sys.exit(main())
