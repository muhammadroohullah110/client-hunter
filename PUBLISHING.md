# How to publish CHunter on GitHub (the "giant leads system")

Your repo already exists: **https://github.com/muhammadroohullah110/client-hunter**

This guide gets the code up there cleanly and makes it the kind of repo people
star. Follow it top to bottom — it takes about 10 minutes.

---

## 0. Before you push — the safety check (do NOT skip)

A lead engine handles business data. **Never** commit any of these — they're
already in `.gitignore`, but verify:

- `.env` — your keys. (Only `.env.example`, with blanks, goes up.)
- `data/leads.db` — real businesses you've scraped/called.
- `audits/`, `out/`, `logs/` — screenshots, PDFs, call outcomes.
- `suppression.csv` once it has real people in it. *(It's tracked now because
  it's empty. If you add real opt-outs, add it to `.gitignore` too.)*

Run this to confirm nothing sensitive is staged:
```bash
git status --short
git check-ignore .env data/leads.db
```
The second command should print both paths (meaning they're ignored). If it
prints nothing, **stop** and fix `.gitignore` before continuing.

---

## 1. Wire up the remote and push

From the project folder (`Desktop/CHunter`):

```bash
git remote add origin https://github.com/muhammadroohullah110/client-hunter.git
git add .
git commit -m "CHunter: zero-cost AU lead engine — find + audit + score (step 1)"
git branch -M main
git push -u origin main
```

If `git remote add` says *"remote origin already exists"*, just run:
```bash
git remote set-url origin https://github.com/muhammadroohullah110/client-hunter.git
```
and continue from `git add .`.

> First push will ask you to sign in to GitHub (browser or a Personal Access
> Token). That's normal.

---

## 2. Make it a repo people find and trust

GitHub ranks repos on description, topics, and README. Do these on the repo page:

**Add a description + topics** (click the ⚙️ next to "About"):
> *Zero-cost lead engine for web-services freelancers: finds local businesses,
> audits their sites, and ranks the few worth calling — no paid APIs.*

Topics (these are search keywords — copy them):
```
lead-generation  cold-outreach  python  openstreetmap  web-audit
lead-scoring  icp-scoring  sales-automation  small-business  zero-cost  australia
```

**Pin the README sections that sell it.** Your README already leads with the
"2,000 → 20" idea and the two-brain diagram — that's your hook. Good.

---

## 3. Optional polish that makes it look "giant" (not required to ship)

Copy the structure the repos you liked used — it's why they look professional:

- **Badges** at the top of the README (license, Python version). Example:
  ```markdown
  ![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
  ![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
  ```
- **A `docs/` folder** with one recipe page per niche (e.g. `docs/dentist-leads.md`)
  — a worked example of finding + qualifying dentists in one city. Great for SEO.
- **`CONTRIBUTING.md`** and **`SECURITY.md`** (even short ones) — signals a
  serious project.
- **A banner image** (`assets/banner.svg`) — the gmaps-kit repo has one you can
  learn the style from.
- **GitHub Actions**: a workflow that runs `python tests/test_engine.py` on every
  push shows a green ✓ and builds trust. (Also the path to running your nightly
  `find→audit→score` in the cloud for free, so it works even when your PC is off.)

Ask me to generate any of these and I'll write them to match your README.

---

## 4. A word on publishing a lead-gen tool (important)

You're publishing a **tool**, which is fine. Keep it that way:

- **Never commit harvested leads or anyone's personal data.** The code is MIT;
  the data you collect with it is not yours to redistribute.
- The README already documents the legal-hygiene rules (robots.txt, published
  contacts only, suppression list, Spam Act identification). Keep that section —
  it's what separates a respectable tool from a spam kit, and it's what a
  reviewer (or a future customer) looks for.
- If you later sell this or a hosted version, swap the MIT license for something
  that fits a commercial product, and get the outreach-compliance wording
  reviewed for the countries you target.

---

## TL;DR

```bash
git remote add origin https://github.com/muhammadroohullah110/client-hunter.git
git add . && git commit -m "CHunter step 1: find + audit + score"
git branch -M main && git push -u origin main
```
Then add the description + topics from section 2. Done — it's live.
