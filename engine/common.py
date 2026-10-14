"""
common.py — shared plumbing for every CHunter module.

Pure Python standard library + PyYAML. No LLM, no paid APIs.
Provides: config/env loading, logging, a polite HTTP fetcher (robots.txt aware,
1 req/sec per domain, real User-Agent carrying your contact email), free
geocoding via Nominatim, grid tiling, and AU phone / domain helpers.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path
from threading import Lock
from typing import Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML missing. Run:  pip install -r requirements.txt")

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"
DATA_DIR = ROOT / "data"
AUDIT_DIR = ROOT / "audits"
OUT_DIR = ROOT / "out"
LOG_DIR = ROOT / "logs"
SUPPRESSION_CSV = ROOT / "suppression.csv"
EXCLUDE_DOMAINS = ROOT / "exclude_domains.txt"

for _d in (DATA_DIR, AUDIT_DIR, OUT_DIR, LOG_DIR):
    _d.mkdir(exist_ok=True)


# ── Config & env ─────────────────────────────────────────────────────────────
_CONFIG_CACHE: Optional[dict] = None


def load_config() -> dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            _CONFIG_CACHE = yaml.safe_load(f) or {}
    return _CONFIG_CACHE


def load_env() -> None:
    """Load KEY=VALUE lines from .env into os.environ (existing vars win)."""
    try:
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                k, sep, v = line.partition("=")
                if sep and k.strip() and k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip().strip("\"'")
    except OSError:
        pass


def contact_email() -> str:
    cfg = load_config()
    return str(cfg.get("my_email", "")).strip() or "contact@example.com"


def user_agent() -> str:
    """Real UA carrying your contact email, as the Spam-Act / crawl-etiquette rules ask."""
    cfg = load_config()
    biz = cfg.get("business_name", "CHunter")
    return f"CHunter/0.1 ({biz}; +mailto:{contact_email()})"


# ── Logging ──────────────────────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)
    try:
        fh = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass
    return log


# ── Polite fetcher ────────────────────────────────────────────────────────────
class PoliteFetcher:
    """HTTP GET that obeys robots.txt and rate-limits to N req/sec per domain.

    One instance is safe to share across threads; per-domain locks serialise
    requests to the same host so we never hammer one site.
    """

    def __init__(self, rps: float = 1.0, timeout: int = 15, obey_robots: bool = True):
        self.min_interval = 1.0 / rps if rps > 0 else 0.0
        self.timeout = timeout
        self.obey_robots = obey_robots
        self._last: dict[str, float] = {}
        self._locks: dict[str, Lock] = {}
        self._robots: dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self._guard = Lock()
        self.log = get_logger("fetch")

    def _lock_for(self, host: str) -> Lock:
        with self._guard:
            return self._locks.setdefault(host, Lock())

    def _robots_for(self, scheme: str, host: str):
        if not self.obey_robots:
            return None
        if host in self._robots:
            return self._robots[host]
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{scheme}://{host}/robots.txt"
        try:
            req = urllib.request.Request(robots_url, headers={"User-Agent": user_agent()})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                rp.parse(resp.read().decode("utf-8", "replace").splitlines())
        except Exception:
            rp = None  # no robots / unreachable → allowed
        self._robots[host] = rp
        return rp

    def allowed(self, url: str) -> bool:
        p = urllib.parse.urlparse(url if "://" in url else "http://" + url)
        rp = self._robots_for(p.scheme or "http", p.netloc)
        if rp is None:
            return True
        try:
            return rp.can_fetch(user_agent(), url)
        except Exception:
            return True

    def get(self, url: str, max_bytes: int = 600_000) -> tuple[int, str, str]:
        """Return (status, final_url, text). status 0 == blocked/failed.

        Respects robots.txt and the per-domain rate limit. Never raises.
        """
        if not url:
            return 0, "", ""
        if "://" not in url:
            url = "http://" + url
        host = urllib.parse.urlparse(url).netloc
        if not self.allowed(url):
            self.log.info("robots.txt blocks %s", url)
            return 0, url, ""
        lock = self._lock_for(host)
        with lock:
            gap = self.min_interval - (time.monotonic() - self._last.get(host, 0.0))
            if gap > 0:
                time.sleep(gap)
            # One retry on a transient failure (status 0) — covers a laptop that
            # briefly slept / dropped Wi-Fi mid-run, which otherwise flatlines a
            # whole nightly batch to HTTP 0.
            try:
                for attempt in range(2):
                    try:
                        req = urllib.request.Request(url, headers={
                            "User-Agent": user_agent(),
                            "Accept": "text/html,application/xhtml+xml",
                            "Accept-Language": "en-AU,en;q=0.9",
                        })
                        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                            text = resp.read(max_bytes).decode("utf-8", "replace")
                            return resp.status, resp.geturl(), text
                    except urllib.error.HTTPError as e:
                        return e.code, url, ""
                    except Exception as e:
                        if attempt == 0:
                            time.sleep(2)
                            continue
                        self.log.debug("fetch failed %s: %s", url, e)
                        return 0, url, ""
                return 0, url, ""
            finally:
                self._last[host] = time.monotonic()


# ── Free geocoding (Nominatim) — adapted from google-maps-scraper-kit ──────────
_NOMINATIM_LAST = [0.0]
_NOMINATIM_LOCK = Lock()


def geocode_city(place: str) -> Optional[tuple[float, float, list[float]]]:
    """City/place name → (lat, lon, bbox[s,n,w,e]) via Nominatim. Free, no key.

    Respects Nominatim's ~1 req/sec policy. Returns None on failure.
    """
    q = urllib.parse.urlencode({"format": "json", "limit": 1, "q": place, "countrycodes": "au"})
    url = f"https://nominatim.openstreetmap.org/search?{q}"
    with _NOMINATIM_LOCK:
        gap = 1.1 - (time.monotonic() - _NOMINATIM_LAST[0])
        if gap > 0:
            time.sleep(gap)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
            with urllib.request.urlopen(req, timeout=30) as resp:
                hits = json.loads(resp.read())
        except Exception:
            return None
        finally:
            _NOMINATIM_LAST[0] = time.monotonic()
    if not hits:
        return None
    h = hits[0]
    bb = h.get("boundingbox")  # Nominatim: [south, north, west, east]
    if not bb:
        return None
    return float(h["lat"]), float(h["lon"]), [float(x) for x in bb]


def grid_cells(bbox: list[float], n: int) -> list[dict]:
    """Split a Nominatim bbox [s,n,w,e] into n×n cells (centre lat/lon + radius m).

    Lifted from google-maps-scraper-kit; lets us tile a big city so one Overpass
    query per tile stays under server timeouts.
    """
    s, nn, w, e = bbox
    dlat, dlon = (nn - s) / n, (e - w) / n
    m_per_deg = 6371000 * math.pi / 180
    cells = []
    for i in range(n):
        for j in range(n):
            lat, lon = s + (i + 0.5) * dlat, w + (j + 0.5) * dlon
            cos = math.cos(math.radians(lat))
            width = max(1.0, dlon * m_per_deg * cos)
            diag = math.hypot(dlat * m_per_deg, width)
            cells.append({
                "lat": lat, "lon": lon,
                "bbox": [s + i * dlat, s + (i + 1) * dlat, w + j * dlon, w + (j + 1) * dlon],
                "radius": max(1000, math.ceil(1.15 * diag / 2)),
            })
    return cells


# ── Domain / phone helpers ─────────────────────────────────────────────────────
def root_domain(url: str) -> str:
    """Normalise a URL/host to its registrable root (strip scheme, www, path)."""
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    # crude eTLD+1: keep last 2 labels, or 3 for .com.au / .net.au / .org.au etc.
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("com", "net", "org", "edu", "gov", "asn", "id") and parts[-1] == "au":
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


_PHONE_CLEAN = re.compile(r"[^\d+]")


def normalize_au_phone(raw: str) -> tuple[str, str]:
    """Return (normalised, type) for an AU number.

    type ∈ {landline, mobile, national, unknown, none}.
    Landlines (02/03/07/08) go on the call sheet; mobiles (04) are flagged
    CHECK_DNCR and held back, per the spec.
    """
    if not raw:
        return "", "none"
    p = _PHONE_CLEAN.sub("", raw)
    if p.startswith("+61"):
        p = "0" + p[3:]
    elif p.startswith("61") and len(p) >= 10:
        p = "0" + p[2:]
    digits = re.sub(r"\D", "", p)
    if digits.startswith(("1300", "1800")) or digits.startswith("13") and len(digits) == 6:
        return digits, "national"
    if digits.startswith("04") and len(digits) == 10:
        return digits, "mobile"
    if digits[:2] in ("02", "03", "07", "08") and len(digits) == 10:
        return digits, "landline"
    if len(digits) >= 8:
        return digits, "unknown"
    return digits, "unknown"


# ── List helpers ────────────────────────────────────────────────────────────────
def load_exclude_domains() -> set[str]:
    out: set[str] = set()
    try:
        with open(EXCLUDE_DOMAINS, encoding="utf-8") as f:
            for line in f:
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    out.add(root_domain(line) or line)
    except OSError:
        pass
    return out


def load_suppression() -> tuple[set[str], set[str], set[str]]:
    """Return (domains, phones, emails) that must never be contacted again."""
    import csv
    doms, phones, emails = set(), set(), set()
    try:
        with open(SUPPRESSION_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("root_domain"):
                    doms.add(root_domain(row["root_domain"]))
                if row.get("phone"):
                    phones.add(re.sub(r"\D", "", row["phone"]))
                if row.get("email"):
                    emails.add(row["email"].strip().lower())
    except OSError:
        pass
    return doms, phones, emails
