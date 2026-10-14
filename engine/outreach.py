"""
outreach.py — TDSOCH's outreach brain. The distilled playbook the system writes
from: cold-email patterns, the cold-DM framework, universal objection handling,
and the live-call structure.

Adapted for TDSOCH's context (a solo web-services operator selling a fixed-price
"Website Speed & Google Fix" to Australian local businesses) from field-tested
frameworks in the training notes:
  • Cold Emails Framework — curiosity / pattern-interrupt subject lines +
    PITCH→OFFER, SHOW VALUE→TRUST, CASE STUDY→PROOF, ASK 15 MINS→CTA, and inbox
    rotation for deliverability.
  • Insta Cold DM Framework — "trojan-horse" opening question → risk-reversal
    pitch → personalised video → CTA.
  • 7FAA live sales-call breakdown — release tension, build credibility fast,
    pre-handle the two big objections, let the prospect name their need, give
    them the reason to justify the buy.
  • VAPI voice-agent prompts — qualify → objection-handle → book → stay compliant.

Everything here is text generation from the lead's REAL audit facts. No LLM
required at runtime; Claude can polish any single piece on request.
"""

from __future__ import annotations

# ── Cold-email subject + opening patterns (curiosity / pattern interrupt) ──────
# Keyed on the lead's biggest finding where it helps; {biz} filled per lead.
SUBJECT_PATTERNS: dict[str, tuple[str, str]] = {
    "low_psi": ("{biz}'s website speed (brutally honest take)",
                "I'll be direct — {biz}'s site is slow on mobile, and that quietly costs you enquiries. One fix changes it."),
    "slow_lcp": ("Is {biz}'s website on vacation?",
                 "Your homepage took its time loading on my phone while faster competitors grab the click first."),
    "no_https": ("Noticed something off with {biz}'s website",
                 "{biz}'s site isn't on a secure connection, so some visitors see a 'Not secure' warning before they even read it."),
    "no_viewport": ("Your website on mobile made me wince (politely)",
                    "{biz}'s site doesn't scale on a phone — which is where most people check you first."),
    "outdated_wp": ("{biz} — this is being left on the table",
                    "{biz}'s website is running old software: slower, and a bit exposed. Quick to fix, big difference."),
    "stale_copyright": ("Confession: I've been looking at your website",
                        "…professionally! {biz}'s site looks like it's been sitting a while, and it's costing you trust."),
    "_default": ("The good news and the 'oops' about {biz}'s website",
                 "Good news: {biz}'s site has real potential. The 'oops': a couple of fixable issues are costing you calls."),
}

# The email skeleton (from the Cold Emails Framework), in order.
EMAIL_SKELETON = ["PITCH → OFFER", "SHOW VALUE → TRUST", "CASE STUDY → PROOF", "ASK FOR 15 MINS → CTA"]


def pick_subject(finding_type: str, biz: str) -> tuple[str, str]:
    subj, opening = SUBJECT_PATTERNS.get(finding_type, SUBJECT_PATTERNS["_default"])
    return subj.format(biz=biz), opening.format(biz=biz)


# ── Cold DM framework (IG / Facebook / LinkedIn) ──────────────────────────────
# Step 1: a trojan-horse question that earns the first reply (low-friction, real).
# Step 2: once they reply, the risk-reversal pitch + offer to send a quick video.
DM_TROJAN_HORSE = [
    "Hey {name} — are you the right person to talk to about {biz}'s website?",
    "Quick one {name}: is {biz}'s site managed in-house or by an agency?",
    "Hi {name}, saw {biz}'s site — who looks after it for you these days?",
]
DM_PITCH = (
    "{name}, what would it mean for {biz} if its website loaded properly on "
    "mobile and the {problem_short} was fixed — done in 48 hours, fixed price, "
    "and if you're not happy you don't pay? I recorded a quick 2-minute screen "
    "video showing the exact issues. Can I send it here?"
)

PROBLEM_SHORT = {
    "low_psi": "slow speed", "slow_lcp": "slow load time", "no_https": "'not secure' warning",
    "no_viewport": "mobile layout", "outdated_wp": "outdated software",
    "stale_copyright": "dated look", "_default": "couple of issues I spotted",
}


def build_dm(name: str, biz: str, finding_type: str, offer_guarantee: bool = True) -> dict:
    """Return {trojan_horse, pitch} — the two DM beats. Guarantee line optional."""
    name = name or "there"
    th = DM_TROJAN_HORSE[0].format(name=name, biz=biz)
    pitch = DM_PITCH.format(name=name, biz=biz, problem_short=PROBLEM_SHORT.get(finding_type, PROBLEM_SHORT["_default"]))
    if not offer_guarantee:
        pitch = pitch.replace(", and if you're not happy you don't pay", "")
    return {"trojan_horse": th, "pitch": pitch, "all_openers": [t.format(name=name, biz=biz) for t in DM_TROJAN_HORSE]}


# ── Universal objection handling (from the live-call breakdown) ────────────────
# Principle: don't get defensive, diffuse, make them hear what they want to hear,
# and give them the reason to justify the purchase. {price}/{hours} filled later.
OBJECTIONS_UNIVERSAL = [
    ("We already have someone / an agency",
     "Perfect — I'm not here to replace them. I fix the specific technical issues most agencies skip, fixed-price. Want the 2-minute audit?"),
    ("We've been burned by agencies before",
     "Honestly, I hear that a lot — which is exactly why I work fixed-price and show you the problems before you pay a cent."),
    ("I want control over my site",
     "You approve everything before it goes live — nothing changes without your say-so."),
    ("Just send me an email",
     "Will do — what's the best address? I'll attach the one-page audit so you can see it in black and white."),
    ("How much is it?",
     "${price} one-off, done in {hours} hours, no lock-in."),
    ("I'm too busy / no time right now",
     "Totally — that's why it's done-for-you. I just need 15 minutes once, then you're hands-off."),
    ("Let me think about it",
     "Of course. So you've got it to show your team: the fix pays for itself the first time it saves one enquiry. Want me to hold a 48-hour slot?"),
]


def universal_objections(price, hours) -> list[tuple[str, str]]:
    return [(o, a.replace("{price}", str(price)).replace("{hours}", str(hours))) for o, a in OBJECTIONS_UNIVERSAL]


# ── Live-call structure (from the 7FAA sales-call breakdown) ───────────────────
CALL_STAGES = [
    ("1. Release the tension",
     "Open warm, not salesy. 'Where are you calling from?' / a line of small talk. "
     "If they sound rushed: 'Are you in a hurry? We can do this later' — it signals your time matters too."),
    ("2. Build credibility fast (first 60 sec)",
     "Drop numbers, don't explain them: sites fixed, years doing this, a before/after. "
     "More numbers = more trust. Then move on — don't talk about yourself longer than you must."),
    ("3. Name the ONE specific problem",
     "Lead with the single biggest audit finding for THIS site (speed, 'not secure', outdated). Concrete, not a list."),
    ("4. Let them name their biggest need",
     "'What's hurting most — the speed, showing up on Google, or getting more bookings?' Then give exactly that."),
    ("5. Pre-handle the two big objections",
     "Before they raise them: (a) 'you stay in control, you approve everything', (b) 'I work fixed-price and show you the issues before you pay'."),
    ("6. Make the offer + the reason to buy",
     "Fixed ${price}, {hours} hours, no lock-in. Give them the line they'll repeat to a partner/staff: 'it pays for itself the first enquiry it saves.'"),
    ("7. Close / next step — read the room",
     "If engaged: book the fix or the follow-up. If distracted/disengaged: don't push — 'I'll send the 2-minute audit', and follow up. Never oversell a cold room."),
]

# ── Deliverability rules (from the Cold Emails Framework) ──────────────────────
SENDING_RULES = [
    "Send from 4–5 rotating inboxes — one inbox blasting volume gets flagged and lands in spam.",
    "Warm new inboxes up before volume; keep daily sends per inbox modest and steady.",
    "Always a curiosity/pattern-interrupt subject line — get the open first.",
    "One specific, real observation per email (from the audit) — never generic 'I checked your site'.",
    "Identify yourself + business + an unsubscribe line every time (AU Spam Act). Skip 'no marketing' sites.",
    "You send; the system only drafts. Review every message before it goes.",
]
