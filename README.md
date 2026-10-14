# TDSOCH — The Damn System Of Client Hunting

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![tests](https://github.com/muhammadroohullah110/client-hunter/actions/workflows/tests.yml/badge.svg)

A **zero-cost, intelligence-first** lead engine for a one-person web-services
business selling to Australian small businesses. Scripts do the grunt work for
free; the handful of personalised messages that actually matter are written from
real audit facts — and you run the whole thing from one beautiful local web app.

> **The whole idea:** don't hand yourself 2,000 raw businesses. Hand yourself
> **~20 pre-qualified ones** that have a real, fixable website problem *and* the
> ability to pay — ranked best-first — so your 7–9 AM calling window is spent
> talking, not sorting.

---

## How the "intelligence" actually works (read this first)

There are **two brains**, and neither one costs money:

| | **Nightly brain** (the filter) | **Morning brain** (the writer) |
|---|---|---|
| What | `find → audit → score` | Claude writes openers + emails |
| When | ~2 AM, automatic | 7 AM, you open Claude Code |
| Runs on | Plain Python, Windows Task Scheduler | Your Claude Pro subscription |
| Cost | **$0** (no APIs, no LLM) | **$0** (included in Pro) |
| Touches | ~2,000 businesses | only the top ~20–25 survivors |

**The "2,000 → 20" intelligence is the Python scoring engine, not an AI.** It
qualifies on real website signals (HTTPS, mobile viewport, outdated WordPress,
stale copyright, PageSpeed, booking widgets, ad pixels, niche lifetime-value).
That's deliberate: it's free, it runs while you sleep, and it never hallucinates.
Claude's expensive intelligence is saved for the one thing scripts can't do well
— writing a human, specific opener for a lead that already passed every gate.

> Claude Code can't run as an always-on background service, and you wouldn't want
> it to — that would be paid API calls on every lead. Task Scheduler runs the
> free Python brain; you run Claude for the final mile.

---

## Pipeline

```
         FREE · AUTOMATIC · NO LLM                      YOU + CLAUDE (free, 7-9 AM)
 ┌─────────────────────────────────────────┐          ┌────────────────────────────┐
 │ find.py ──▶ audit.py ──▶ score.py        │          │ write.py  (openers/emails) │
 │ OSM leads   website      hard gates +    │  top ~20 │ callsheet.py (your screen) │
 │ (free)      audit        0-100 ranking   │ ───────▶ │ followup.py (Gmail drafts) │
 └─────────────────────────────────────────┘          └────────────────────────────┘
        stored in SQLite (data/leads.db)
```

**Build status: complete.** All 7 steps built and tested (14/14):
find → audit → score (nightly brain) · call sheet · write (openers/emails) ·
follow-up drafts · delivery playbook · dashboard · scheduling — all surfaced
through one local web app (`python tdsoch.py serve`).

---

## What each module does

| Module | Job | LLM? |
|--------|-----|------|
| [`engine/find.py`](engine/find.py) | Discover businesses from **OpenStreetMap Overpass** (free, no key) by city × niche, keep only those with a website, de-dupe, drop chains/suppressed, optional free **ABN** check | No |
| [`engine/audit.py`](engine/audit.py) | Fetch each site politely (robots.txt, 1 req/s, contact-email UA); record HTTPS / viewport / WordPress+version / title / meta / tel / form / page weight / image dims / internal-link count; detect **booking widgets** & **ad pixels** (budget signals); harvest **published** emails + socials; optional **PageSpeed**; optional screenshot; derive severity-tagged findings | No |
| [`engine/score.py`](engine/score.py) | **Hard gates** (reachable · not a chain · has a fixable problem · can pay) → qualified; then a **0–100 rank** across 6 weighted dimensions so biggest-pain + best-payer surface first | No |
| [`engine/callsheet.py`](engine/callsheet.py) | Your **7 AM screen**: a local web page (stdlib server, no Flask) with one card per qualified lead — local time, click-to-call, opener, top findings, objection hints, and one-click outcome buttons (keys 1–6) that log straight to SQLite; `NOT_INTERESTED` auto-adds to `suppression.csv` | No |
| [`engine/write.py`](engine/write.py) | Drafts a **spoken call opener** (≤40 words, built from the lead's biggest real finding), objection scripts, a **Spam-Act-compliant email**, and a one-page HTML audit — facts only, never invented numbers | Template (Claude-polishable) |
| [`engine/followup.py`](engine/followup.py) | Prepares `.eml` email drafts (audit attached) you review and send yourself — **never auto-sends**; NO_ANSWER requeues after 2 business days (max 3), callbacks surface on their day; optional Gmail-API drafts | No |
| [`engine/deliver.py`](engine/deliver.py) | For a SOLD lead: an audit-specific **fix playbook** (backup first, then the exact fixes), a **before/after** re-audit, and an upsell-email draft | No |
| [`engine/dashboard.py`](engine/dashboard.py) | The funnel scoreboard: found→…→sold, conversion vs the §4 targets, 7-day trend, revenue (A$ + ₨), and red flags when a step underperforms | No |
| [`engine/webapp.py`](engine/webapp.py) + [`webui.py`](engine/webui.py) | **The web app** — one beautiful local UI over everything: Dashboard, Call Sheet, Leads, and per-lead detail, with one-click outcome logging and on-demand opener/email writing | No |
| [`engine/common.py`](engine/common.py) | Config/env, logging, the polite fetcher, free Nominatim geocoding, grid tiling, AU phone/domain helpers | No |
| [`engine/db.py`](engine/db.py) | SQLite schema + helpers (the data contract every module shares) | No |

### The scoring model (how a lead qualifies)

A lead is **QUALIFIED** only if it clears *every* gate (configurable in `config.yaml`):

1. **Reachable** — site responds 200–399.
2. **Not a chain** — root domain not in `exclude_domains.txt`.
3. **Has a visible, fixable problem** — any of: no HTTPS, no mobile viewport,
   outdated WordPress, stale copyright year, low PageSpeed, slow LCP.
4. **Can pay** — has a phone **and** a size/spend signal (≥5 pages, online
   booking, ad pixels, or a high-value niche like dentist/physio/accountant).

Qualified leads are then ranked 0–100:

| Dimension | Max | Reads |
|-----------|-----|-------|
| Ability to pay | 30 | niche LTV tier + booking + ads + page count + reviews |
| Pain severity | 35 | severity-weighted unique findings |
| Reachability | 15 | published email + tel link + contact form |
| Digital maturity | 10 | blog + social + schema |
| Opportunity | 10 | stale year + outdated WP + very low PSI |

> Scoring logic is adapted from the open-source **opengtm** `qualify.py`
> (MIT) — a signal-based ICP scorer — retuned for AU local businesses. The
> email/social harvesting technique is adapted from **google-maps-scraper-kit**
> (MIT). We **do not** use their Google-Maps-HTML scraping or any paid API; lead
> discovery is OpenStreetMap only, per our legal-hygiene rules. Credits in
> [CREDITS.md](CREDITS.md).

---

## Setup (non-developer friendly)

### 1. Install Python 3.11+
Download from [python.org](https://www.python.org/downloads/), tick **"Add
Python to PATH"** during install.

### 2. Install dependencies
Open **PowerShell** in this folder and run:
```bash
pip install -r requirements.txt
```
(Optional, only if you want homepage screenshots:)
```bash
playwright install chromium
```

### 3. Fill in your details
- Open `config.yaml`, replace every `[BRACKET]` (business name, your name/email,
  phone, payment link). Pick your starting cities and niches.
- Copy `.env.example` to `.env`. All keys are **optional and free** — leave them
  blank to start. A free [PSI_KEY](https://developers.google.com/speed/docs/insights/v5/get-started)
  makes the PageSpeed gates work; a free [ABN_GUID](https://abr.business.gov.au/Tools/WebServices)
  verifies businesses are active.

### 4. Test it
```bash
python tdsoch.py run --city Brisbane --niche dentist --limit 20 --no-screenshot
python tdsoch.py write
python tdsoch.py serve
```
First command finds → audits → ranks; `write` drafts the openers/emails; `serve`
opens the web app at http://localhost:8700. Run the tests with
`python tests/test_engine.py`.

### 5. Automate the nightly run (while you sleep)
Easiest — from PowerShell in this folder:
```bash
.\scripts\install_task.ps1
```
That registers a **"TDSOCH Nightly"** task (daily 2 AM, wakes the PC, catches up
if it was off). Logs land in `logs/nightly.log`. Remove it with
`Unregister-ScheduledTask -TaskName "TDSOCH Nightly" -Confirm:$false`.

Prefer the cloud (runs even when your PC is off)? Run the nightly on a **private**
fork via GitHub Actions — never on the public repo, so leads stay private.

> **Laptop tip:** if the machine sleeps mid-run, some fetches fail that night
> (the engine retries once and recovers next run). For a 100% reliable 2 AM run,
> keep the laptop awake/plugged in, or move the nightly job to a free GitHub
> Actions workflow (planned).

---

## Command cheat-sheet

One entry point, `tdsoch.py`:

```bash
python tdsoch.py run            # nightly brain: find -> audit -> score (free, no LLM)
python tdsoch.py write          # draft openers + emails + audits for the queue
python tdsoch.py serve          # open the web app (Dashboard / Call Sheet / Leads)
python tdsoch.py morning        # write + serve — your 7 AM one-liner
python tdsoch.py followup       # prepare .eml drafts + requeue (never auto-sends)
python tdsoch.py dashboard      # funnel metrics + out/dashboard.html
python tdsoch.py deliver --lead 12            # fix playbook for a SOLD lead
python tdsoch.py deliver --lead 12 --reaudit  # before/after report
```

Flags pass straight through, e.g.
`python tdsoch.py run --city Brisbane --niche dentist --limit 20 --no-screenshot`.

Modules still run directly too (`python -m engine.find --dry-run`,
`python -m engine.audit --limit 10 --psi`, …). Every module supports
`--dry-run`. **Nothing is ever emailed or called automatically — the system only
prepares. You call, you click, you send.**

Run the tests any time: `python tests/test_engine.py` (14 tests, offline).

---

## Legal & etiquette (built in)

- Contacts **only** business details the business itself published (website,
  listing). Never personal profiles.
- Obeys `robots.txt`, 1 request/second per domain, real User-Agent with your
  contact email.
- Sites that say "no unsolicited marketing" are flagged `do_not_email`.
- `suppression.csv` is honoured on every run — anyone who opts out is never
  contacted again, by any channel.
- Mobile numbers (04xx) are flagged `CHECK_DNCR` and held off the call sheet.
- Lead discovery uses OpenStreetMap, **not** Google Maps / Yellow Pages HTML.

---

## License

MIT — see [LICENSE](LICENSE). Built with Claude Code.
