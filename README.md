# CHunter — Audit → Call → Fix Lead Engine

A **zero-cost, intelligence-first** lead engine for a one-person web-services
business selling to Australian small businesses. Scripts do the grunt work for
free; an AI writes the handful of personalised messages that actually matter.

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

**Build status:** Step 1 (`find` + `audit` + `score`) is complete and tested.
Steps 2–7 (callsheet, write, follow-up drafts, dashboard, scheduling polish,
delivery playbook) are next.

---

## What each module does

| Module | Job | LLM? |
|--------|-----|------|
| [`engine/find.py`](engine/find.py) | Discover businesses from **OpenStreetMap Overpass** (free, no key) by city × niche, keep only those with a website, de-dupe, drop chains/suppressed, optional free **ABN** check | No |
| [`engine/audit.py`](engine/audit.py) | Fetch each site politely (robots.txt, 1 req/s, contact-email UA); record HTTPS / viewport / WordPress+version / title / meta / tel / form / page weight / image dims / internal-link count; detect **booking widgets** & **ad pixels** (budget signals); harvest **published** emails + socials; optional **PageSpeed**; optional screenshot; derive severity-tagged findings | No |
| [`engine/score.py`](engine/score.py) | **Hard gates** (reachable · not a chain · has a fixable problem · can pay) → qualified; then a **0–100 rank** across 6 weighted dimensions so biggest-pain + best-payer surface first | No |
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
python run_step1.py --city Brisbane --niche dentist --limit 20 --no-screenshot
```
You'll see leads found → audited → a ranked "TODAY QUEUE" of the qualified ones.
Run the test suite any time with:
```bash
python tests/test_engine.py
```

### 5. Automate it (runs while you sleep)
Open **Task Scheduler** → *Create Basic Task* → name it "CHunter nightly" →
trigger **Daily at 2:00 AM** → action **Start a program** → browse to
`run_all.bat` in this folder → finish. Tick *"Run whether user is logged on or
not"* and, under *Conditions*, untick *"Start only on AC power"* if you're on a
laptop. Logs land in `logs/nightly.log`.

> **Laptop tip:** if the machine sleeps mid-run, some fetches fail that night
> (the engine retries once and recovers next run). For a 100% reliable 2 AM run,
> keep the laptop awake/plugged in, or move the nightly job to a free GitHub
> Actions workflow (planned).

---

## Command cheat-sheet

```bash
python run_step1.py                         # full nightly pipeline (uses config.yaml)
python run_step1.py --limit 20 --no-screenshot   # quick test run
python -m engine.find   --dry-run           # find only, print, write nothing
python -m engine.audit  --limit 10 --psi    # audit 10, with PageSpeed on
python -m engine.score  --show 25           # re-score, print top 25 queue
python tests/test_engine.py                 # 11 tests, offline
```

Every module supports `--dry-run`. Nothing is ever emailed or called
automatically — the engine only *prepares*.

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
