# TDSOCH Outreach Playbook

The outreach brain behind TDSOCH, distilled from field-tested frameworks and
**adapted to our context**: a solo operator selling a fixed-price *Website Speed
& Google Fix* to Australian local businesses (dentists, physios, accountants,
trades). The system generates every message from a lead's **real audit facts** —
never invented numbers.

Code home: [`engine/outreach.py`](../engine/outreach.py). Used by `write.py`
(emails + DMs), `callsheet.py` (objections), and the call sheet UI.

---

## 1. The call (phone-first — our main channel)

From a live sales-call breakdown. Seven stages, in order:

1. **Release the tension.** Open warm, not salesy — "Where are you calling from?", a line of small talk. The prospect arrived braced to be pitched; defuse that first. If they sound rushed: *"Are you in a hurry? We can do this later"* — it signals your time matters too.
2. **Build credibility fast (first 60 seconds).** Drop numbers, don't explain them: sites fixed, years doing this, a before/after. More numbers = more trust. Then move on — don't talk about yourself longer than you must.
3. **Name the ONE specific problem.** Lead with the single biggest finding for *this* site (speed, "not secure", outdated software). Concrete, not a laundry list.
4. **Let them name their biggest need.** *"What's hurting most — the speed, showing up on Google, or getting more bookings?"* Then give exactly that.
5. **Pre-handle the two big objections** before they're raised: (a) *you stay in control, you approve everything*; (b) *I work fixed-price and show you the issues before you pay*.
6. **Make the offer + the reason to buy.** Fixed price, 48 hours, no lock-in. Hand them the line they'll repeat to a partner/staff: *"it pays for itself the first enquiry it saves."*
7. **Close / next step — read the room.** Engaged → book the fix or follow-up. Distracted → don't push: *"I'll send the 2-minute audit"*, then follow up. Never oversell a cold room.

> The call sheet shows the opener + top findings + objections per lead so you
> run these stages live.

## 2. Objection handling (universal)

Principle: **don't get defensive, diffuse, make them hear what they want to hear,
and give them the reason to justify the buy.**

| They say | You say |
|---|---|
| "We already have someone / an agency" | "I'm not here to replace them — I fix the specific technical issues most agencies skip, fixed-price. Want the 2-min audit?" |
| "We've been burned by agencies before" | "I hear that a lot — which is exactly why I work fixed-price and show you the problems before you pay a cent." |
| "I want control over my site" | "You approve everything before it goes live — nothing changes without your say-so." |
| "Just send me an email" | "Will do — what's the best address? I'll attach the one-page audit." (then *actually* follow up) |
| "How much?" | "$[price] one-off, [hours] hours, no lock-in." |
| "I'm too busy" | "That's why it's done-for-you — I need 15 minutes once, then you're hands-off." |
| "Let me think about it" | "Of course — so you've got it for your team: it pays for itself the first enquiry it saves. Want me to hold a 48-hour slot?" |

## 3. Cold email

**Get the open first** with a curiosity / pattern-interrupt subject line, then a
specific real observation. Structure the body as:
**PITCH → OFFER · SHOW VALUE → TRUST · CASE STUDY → PROOF · ASK 15 MINS → CTA.**

Our subject patterns (filled per lead from the top finding) live in
`outreach.SUBJECT_PATTERNS`, e.g.:

- *"[biz]'s website speed (brutally honest take)"*
- *"Is [biz]'s website on vacation?"*
- *"[biz] — this is being left on the table"*
- *"The good news and the 'oops' about [biz]'s website"*

**Deliverability rules (non-negotiable):**

- Send from **4–5 rotating inboxes** — one inbox doing volume gets flagged and lands in spam. Warm new inboxes up first; keep per-inbox volume modest and steady.
- One **specific** observation per email (from the audit) — never generic.
- Every email: identify yourself + business + an unsubscribe line (AU **Spam Act 2003**). Skip any site that says "no unsolicited/marketing".
- **The system drafts; you send.** Review every message.

## 4. Cold DM (Instagram / Facebook / LinkedIn)

Two beats:

1. **Trojan-horse question** — low-friction and real, to earn the first reply:
   *"Hey [name] — are you the right person to talk to about [biz]'s website?"*
2. **Once they reply, risk-reversal pitch + video offer:**
   *"[name], what would it mean for [biz] if its website loaded properly on mobile and the [problem] was fixed — done in 48 hours, fixed price, and if you're not happy you don't pay? I recorded a quick 2-minute screen video showing the exact issues. Can I send it here?"*

Then send the personalised video (a 2-min screen recording of their real issues),
get their email, book the call. The guarantee line is optional — only promise
what you'll honour.

> `write.py` generates a trojan-horse + pitch DM per lead; it shows on the Lead
> detail page. **Contact only business accounts/published handles — never
> personal profiles — and respect platform limits.**

## 5. What TDSOCH automates vs. what you do

TDSOCH **prepares** — openers, objection scripts, emails, DMs, audits — all from
real facts. **You** make the call, click the outcome, and hit send. Nothing is
auto-dialled or auto-sent. That's deliberate: it keeps you compliant, keeps
quality high, and keeps the cost at zero.

---

*Adapted from: Cold Emails Framework, Insta Cold DM Framework, a 7FAA live
sales-call breakdown, and VAPI voice-agent prompts (training notes). Techniques
only — reworked for AU local-business web services. See
[CREDITS.md](../CREDITS.md).*
