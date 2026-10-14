"""
find.py — free lead discovery via OpenStreetMap Overpass. No API key, no cost.

For each (city, niche) it asks Overpass for businesses carrying that niche's tags
AND a website tag, collects name/website/phone/address/coords, de-dupes on root
domain + phone, drops anything on the suppression/exclude lists, and stores new
leads in SQLite. Optional ABN verification if ABN_GUID is set.

    python -m engine.find                 # all configured cities × niches
    python -m engine.find --dry-run       # fetch + parse, print, write nothing
    python -m engine.find --city Brisbane --niche dentist --limit 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

from . import db
from .common import (get_logger, load_config, load_env, load_exclude_domains,
                     load_suppression, normalize_au_phone, root_domain, user_agent)

log = get_logger("find")

# Several public Overpass mirrors; we rotate on failure because any one of them
# can be overloaded (504) at a given moment. Order = try first → last.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

# Each niche → the OSM tag filters that identify it. We only keep POIs that also
# carry a website, since the whole engine is a website audit.
NICHE_TAGS: dict[str, list[str]] = {
    "dentist": ['["amenity"="dentist"]', '["healthcare"="dentist"]'],
    "physiotherapist": ['["healthcare"="physiotherapist"]', '["healthcare:speciality"="physiotherapy"]'],
    "accountant": ['["office"="accountant"]', '["office"="tax_advisor"]'],
    "plumber": ['["craft"="plumber"]'],
    "electrician": ['["craft"="electrician"]'],
}


def build_query(bbox_sn_we: tuple[float, float, float, float], tag_filters: list[str], timeout: int = 90) -> str:
    """Overpass QL: nodes+ways+relations with each tag filter AND a website, in bbox."""
    s, n, w, e = bbox_sn_we
    bbox = f"{s},{w},{n},{e}"  # Overpass wants south,west,north,east
    # nwr = node+way+relation in one directive; `nw` would skip relations but
    # businesses are nodes/ways in practice, so we query node+way to keep the
    # load (and timeout risk) down on busy public servers.
    parts = []
    for tf in tag_filters:
        for kind in ("node", "way"):
            parts.append(f'  {kind}{tf}["website"]({bbox});')
            parts.append(f'  {kind}{tf}["contact:website"]({bbox});')
    body = "\n".join(parts)
    return f"[out:json][timeout:{timeout}];\n(\n{body}\n);\nout center tags;"


def overpass(query: str, timeout: int = 120) -> list[dict]:
    """POST the query to each mirror in turn until one answers. Public Overpass
    endpoints throttle hard under load (504 / read timeout), so rotating mirrors
    is what keeps the nightly find step from coming back empty."""
    data = urllib.parse.urlencode({"data": query}).encode()
    for i, mirror in enumerate(OVERPASS_MIRRORS):
        try:
            req = urllib.request.Request(mirror, data=data, headers={"User-Agent": user_agent()})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                els = json.loads(resp.read()).get("elements", [])
            log.info("  Overpass OK via %s (%d elements)", urllib.parse.urlparse(mirror).netloc, len(els))
            return els
        except Exception as e:
            log.warning("  Overpass mirror %s failed (%s)", urllib.parse.urlparse(mirror).netloc, e)
            if i < len(OVERPASS_MIRRORS) - 1:
                time.sleep(3)
    log.error("Overpass failed on all %d mirrors", len(OVERPASS_MIRRORS))
    return []


def _tag(el: dict, *keys: str) -> str:
    t = el.get("tags", {})
    for k in keys:
        if t.get(k):
            return str(t[k]).strip()
    return ""


def element_to_lead(el: dict, niche: str, city: str) -> dict | None:
    t = el.get("tags", {})
    website = _tag(el, "website", "contact:website")
    if not website:
        return None
    rd = root_domain(website)
    if not rd:
        return None
    phone_raw = _tag(el, "phone", "contact:phone", "contact:mobile")
    phone, ptype = normalize_au_phone(phone_raw)
    # address from addr:* tags
    hn, st = _tag(el, "addr:housenumber"), _tag(el, "addr:street")
    suburb = _tag(el, "addr:suburb", "addr:city")
    addr = " ".join(x for x in [f"{hn} {st}".strip(), suburb, _tag(el, "addr:postcode")] if x)
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    return {
        "name": _tag(el, "name") or rd,
        "root_domain": rd,
        "website": website if "://" in website else "http://" + website,
        "phone": phone,
        "phone_type": ptype,
        "email": _tag(el, "email", "contact:email"),
        "address": addr,
        "suburb": suburb,
        "lat": lat,
        "lon": lon,
        "niche": niche,
        "city": city,
        "source": "osm",
        "abn_status": "skipped",
        "rating": None,
        "review_count": None,
    }


# ── ABN verification (optional, free) ────────────────────────────────────────
def verify_abn(name: str, guid: str) -> str:
    """Return 'active' | 'cancelled' | 'unknown' using the free ABR web service.
    Best-effort name search; never blocks the pipeline."""
    if not guid or not name:
        return "skipped"
    q = urllib.parse.urlencode({"name": name, "guid": guid, "maxResults": 1})
    url = f"https://abr.business.gov.au/json/MatchingNames.aspx?{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", "replace")
        m = re.search(r"\{.*\}", raw, re.S)  # response is JSONP: callback({...})
        if not m:
            return "unknown"
        names = json.loads(m.group(0)).get("Names", [])
        if not names:
            return "unknown"
        state = (names[0].get("AbnStatus") or "").lower()
        return "active" if "active" in state else ("cancelled" if "cancel" in state else "unknown")
    except Exception:
        return "unknown"


def find(cities: list[str] | None = None, niches: list[str] | None = None,
         limit: int | None = None, dry_run: bool = False) -> int:
    from .common import geocode_city  # local import keeps module import cheap
    load_env()
    cfg = load_config()
    cities = cities or cfg.get("cities", [])
    niches = niches or cfg.get("niches", [])
    abn_guid = __import__("os").environ.get("ABN_GUID", "").strip()

    sup_doms, sup_phones, sup_emails = load_suppression()
    excluded = load_exclude_domains()
    db.init_db()

    seen_domains: set[str] = set()
    seen_phones: set[str] = set()
    found_total = new_total = 0

    for city in cities:
        geo = geocode_city(city)
        if not geo:
            log.warning("Could not geocode %s — skipping", city)
            continue
        _, _, bbox = geo  # [s,n,w,e]
        bbox_t = (bbox[0], bbox[1], bbox[2], bbox[3])
        for niche in niches:
            tags = NICHE_TAGS.get(niche)
            if not tags:
                log.warning("No OSM tags mapped for niche '%s' — skipping", niche)
                continue
            log.info("Overpass: %s in %s", niche, city)
            elements = overpass(build_query(bbox_t, tags))
            log.info("  %d raw elements", len(elements))

            with db.connect() as conn:
                for el in elements:
                    lead = element_to_lead(el, niche, city)
                    if not lead:
                        continue
                    rd, ph = lead["root_domain"], re.sub(r"\D", "", lead["phone"] or "")
                    # de-dupe (this run) + suppression + chain exclusion
                    if rd in seen_domains or (ph and ph in seen_phones):
                        continue
                    if rd in sup_doms or rd in excluded:
                        continue
                    if ph and ph in sup_phones:
                        continue
                    if lead["email"] and lead["email"].lower() in sup_emails:
                        continue
                    seen_domains.add(rd)
                    if ph:
                        seen_phones.add(ph)
                    found_total += 1

                    if abn_guid and not dry_run:
                        lead["abn_status"] = verify_abn(lead["name"], abn_guid)
                        if lead["abn_status"] == "cancelled":
                            continue  # skip dead businesses

                    if dry_run:
                        log.info("  [dry] %s | %s | %s (%s)", lead["name"], rd,
                                 lead["phone"] or "—", lead["phone_type"])
                    else:
                        if db.upsert_lead(conn, lead) is not None:
                            new_total += 1

                    if limit and found_total >= limit:
                        break
            if limit and found_total >= limit:
                break
        if limit and found_total >= limit:
            break

    log.info("find complete: %d unique seen, %d new stored%s",
             found_total, new_total, " (dry-run: nothing written)" if dry_run else "")
    return new_total


def main() -> None:
    ap = argparse.ArgumentParser(description="Find leads from OpenStreetMap (free).")
    ap.add_argument("--city", action="append", help="override configured cities (repeatable)")
    ap.add_argument("--niche", action="append", help="override configured niches (repeatable)")
    ap.add_argument("--limit", type=int, help="stop after N unique leads (testing)")
    ap.add_argument("--dry-run", action="store_true", help="fetch + print, write nothing")
    a = ap.parse_args()
    find(cities=a.city, niches=a.niche, limit=a.limit, dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
