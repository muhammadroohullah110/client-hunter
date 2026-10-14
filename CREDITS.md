# Credits & attributions

CHunter stands on the shoulders of several open-source projects. We reused
**ideas and techniques**, not paid services, and kept everything zero-cost.

### opengtm — https://github.com/buildingopen/opengtm  (MIT)
- **What we adapted:** the signal-based ICP scoring model from `qualify.py` — a
  0–100 score derived purely from website audit signals, no manual data entry.
  We retuned its dimensions and industry tiers for Australian local businesses
  and added hard qualification gates on top.
- **What we did NOT use:** its `discover.py` / `research.py`, which call the
  Gemini API. CHunter is zero-paid-API, so lead discovery uses OpenStreetMap
  instead.

### google-maps-scraper-kit — https://github.com/Mahanaicoach/google-maps-scraper-kit  (MIT)
- **What we adapted:** the pure-stdlib, zero-LLM enrichment techniques —
  email extraction (mailto + text regex, junk filtering, on-site-domain ranking,
  deep pass over contact/about pages), social-handle extraction with a
  handle skip-list, Nominatim geocoding, and the grid-tiling / dedupe helpers.
- **What we did NOT use:** its core Google-Maps-HTML scraping engine (the Docker
  service). Scraping Google Maps HTML is against our legal-hygiene rules, so
  CHunter discovers leads from OpenStreetMap only.

### Lead-Generation-System-using-Google-Map — https://github.com/Awaisali36/Lead-Generation-System-using-Google-Map  (MIT)
- **What we took:** two *ideas* only — using Google rating + review count as
  ability-to-pay signals, and a clean lead-field schema.
- **What we did NOT use:** its implementation (n8n + Serper.dev + GPT-4o +
  Perplexity ≈ $0.92–1.55 per 100 leads). All paid APIs — excluded by design.

### Tools
- **OpenStreetMap / Overpass API** — free lead source. © OpenStreetMap
  contributors, ODbL.
- **Nominatim** — free geocoding. Used within its ~1 req/sec usage policy.
- **Google PageSpeed Insights v5** — optional, free tier.
- **Australian Business Register (ABN Lookup)** — optional, free web service.

Built with [Claude Code](https://claude.com/claude-code).
