"""
db.py — SQLite schema + helpers. One file owns the data contract so every
module (find / audit / score / callsheet / followup) reads and writes the same
shapes. Pure stdlib.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .common import DATA_DIR

DB_PATH = DATA_DIR / "leads.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT,
    root_domain   TEXT UNIQUE,
    website       TEXT,
    phone         TEXT,
    phone_type    TEXT,                 -- landline|mobile|national|unknown|none
    email         TEXT,
    address       TEXT,
    suburb        TEXT,
    lat           REAL,
    lon           REAL,
    niche         TEXT,
    city          TEXT,
    source        TEXT,                 -- osm|abn|places
    abn_status    TEXT,                 -- active|cancelled|unknown|skipped
    rating        REAL,                 -- Google/OSM stars if known (ability-to-pay signal)
    review_count  INTEGER,
    status        TEXT DEFAULT 'new',   -- new|audited|scored|suppressed
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS audits (
    lead_id         INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    http_status     INTEGER,
    final_url       TEXT,
    https_ok        INTEGER,            -- 0/1
    redirect_chain  TEXT,
    is_wordpress    INTEGER,
    wp_version      TEXT,
    has_viewport    INTEGER,
    footer_year     INTEGER,
    page_weight     INTEGER,            -- bytes of homepage HTML
    imgs_no_dims    INTEGER,
    internal_links  INTEGER,            -- distinct same-site links (page-count proxy)
    has_title       INTEGER,
    title_text      TEXT,
    has_meta_desc   INTEGER,
    has_tel         INTEGER,
    has_form        INTEGER,
    has_blog        INTEGER,
    has_social      INTEGER,
    has_schema      INTEGER,
    has_booking     INTEGER,            -- cliniko/hotdoc/healthengine/calendly etc.
    has_ads_tag     INTEGER,            -- gtag/AW-/fbq pixel (spends on marketing)
    instagram       TEXT,
    facebook        TEXT,
    linkedin        TEXT,
    emails_found    TEXT,               -- comma-separated, published business emails only
    psi_perf        INTEGER,            -- PageSpeed mobile 0-100
    lcp             REAL,               -- seconds
    cls             REAL,
    tbt             REAL,               -- ms
    do_not_email    INTEGER,            -- site says "no unsolicited/marketing"
    findings_json   TEXT,               -- [{type,severity,detail}]
    screenshot_path TEXT,
    audited_at      TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    lead_id       INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    score         INTEGER,              -- 0-100 ranking score
    qualified     INTEGER,              -- 0/1 passed every hard gate
    tier          TEXT,                 -- hot|warm|cold
    top_problem   TEXT,                 -- headline sellable problem
    gates_json    TEXT,                 -- which gates passed/failed + why
    breakdown_json TEXT,                -- per-dimension points
    reason        TEXT,                 -- human one-liner
    scored_at     TEXT
);

CREATE TABLE IF NOT EXISTS outcomes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     INTEGER REFERENCES leads(id) ON DELETE CASCADE,
    status      TEXT,   -- NO_ANSWER|GATEKEEPER|NOT_INTERESTED|SEND_AUDIT|CALLBACK|SOLD
    note        TEXT,
    callback_at TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
    lead_id       INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    opener        TEXT,
    objections    TEXT,
    email_subject TEXT,
    email_body    TEXT,
    pdf_path      TEXT,
    state         TEXT,   -- draft|ready|sent
    created_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_scores_rank  ON scores(qualified, score);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive, idempotent schema upgrades (safe to run every start)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(drafts)")}
    if "dm" not in cols:
        conn.execute("ALTER TABLE drafts ADD COLUMN dm TEXT")  # cold DM draft (IG/FB/LinkedIn)


# ── leads ─────────────────────────────────────────────────────────────────────
def upsert_lead(conn: sqlite3.Connection, lead: dict) -> Optional[int]:
    """Insert a lead keyed on root_domain. Returns lead id, or None if it already
    existed (so callers can count genuinely new leads)."""
    now = _now()
    cols = ("name", "root_domain", "website", "phone", "phone_type", "email", "address",
            "suburb", "lat", "lon", "niche", "city", "source", "abn_status",
            "rating", "review_count")
    vals = [lead.get(c) for c in cols]
    try:
        cur = conn.execute(
            f"INSERT INTO leads ({','.join(cols)}, status, created_at, updated_at) "
            f"VALUES ({','.join('?' * len(cols))}, 'new', ?, ?)",
            (*vals, now, now),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # duplicate root_domain


def set_lead_status(conn: sqlite3.Connection, lead_id: int, status: str) -> None:
    conn.execute("UPDATE leads SET status=?, updated_at=? WHERE id=?", (status, _now(), lead_id))


def leads_needing(conn: sqlite3.Connection, stage: str) -> list[sqlite3.Row]:
    """stage='audit' → status new; stage='score' → status audited."""
    want = {"audit": "new", "score": "audited"}[stage]
    return list(conn.execute("SELECT * FROM leads WHERE status=? ORDER BY id", (want,)))


# ── audits ──────────────────────────────────────────────────────────────────────
def save_audit(conn: sqlite3.Connection, lead_id: int, audit: dict) -> None:
    audit = dict(audit)
    audit["lead_id"] = lead_id
    audit["audited_at"] = _now()
    if isinstance(audit.get("findings_json"), (list, dict)):
        audit["findings_json"] = json.dumps(audit["findings_json"], ensure_ascii=False)
    keys = [k for k in audit if k in _AUDIT_COLS]
    conn.execute(
        f"INSERT OR REPLACE INTO audits ({','.join(keys)}) VALUES ({','.join('?' * len(keys))})",
        [audit[k] for k in keys],
    )


_AUDIT_COLS = {
    "lead_id", "http_status", "final_url", "https_ok", "redirect_chain", "is_wordpress",
    "wp_version", "has_viewport", "footer_year", "page_weight", "imgs_no_dims", "internal_links",
    "has_title", "title_text", "has_meta_desc", "has_tel", "has_form", "has_blog", "has_social",
    "has_schema", "has_booking", "has_ads_tag", "instagram", "facebook", "linkedin",
    "emails_found", "psi_perf", "lcp", "cls", "tbt", "do_not_email", "findings_json",
    "screenshot_path", "audited_at",
}


def audit_for(conn: sqlite3.Connection, lead_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM audits WHERE lead_id=?", (lead_id,)).fetchone()


# ── scores ───────────────────────────────────────────────────────────────────────
def save_score(conn: sqlite3.Connection, lead_id: int, score: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO scores "
        "(lead_id, score, qualified, tier, top_problem, gates_json, breakdown_json, reason, scored_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (lead_id, score["score"], int(score["qualified"]), score["tier"], score.get("top_problem", ""),
         json.dumps(score.get("gates", {})), json.dumps(score.get("breakdown", {})),
         score.get("reason", ""), _now()),
    )


def today_queue(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """Qualified leads, best first, with their audit — the morning call list."""
    return list(conn.execute(
        "SELECT l.*, s.score, s.tier, s.top_problem, s.reason "
        "FROM scores s JOIN leads l ON l.id = s.lead_id "
        "WHERE s.qualified = 1 ORDER BY s.score DESC, s.lead_id LIMIT ?",
        (limit,),
    ))


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    def one(sql: str, args: Iterable[Any] = ()) -> int:
        return conn.execute(sql, tuple(args)).fetchone()[0]
    return {
        "leads": one("SELECT COUNT(*) FROM leads"),
        "audited": one("SELECT COUNT(*) FROM audits"),
        "scored": one("SELECT COUNT(*) FROM scores"),
        "qualified": one("SELECT COUNT(*) FROM scores WHERE qualified=1"),
    }
