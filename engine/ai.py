"""
ai.py — optional AI layer (bring your own key). OFF by default, so the system
stays zero-cost. When a user adds an API key in Settings, the engine can use a
free/paid LLM to: write sharper openers/emails, and produce an expert audit
verdict + prioritised fixes (SkyGen-style).

OpenAI-compatible, so it works with Groq, OpenRouter, OpenAI, Together, or any
custom base URL. The API key lives in .env (git-ignored) — never in config.yaml.
Every call is best-effort: on any error it returns None and the caller falls
back to the free deterministic path.
"""

from __future__ import annotations

import json
import os
import urllib.request

from .common import get_logger, load_config, load_env

log = get_logger("ai")

# Provider presets: base URL + a sensible default model + free fallbacks.
PROVIDERS = {
    "groq": {"base": "https://api.groq.com/openai/v1",
             "model": "openai/gpt-oss-120b",
             "fallbacks": ["openai/gpt-oss-20b", "llama-3.3-70b-versatile"]},
    "openrouter": {"base": "https://openrouter.ai/api/v1",
                   "model": "google/gemma-2-9b-it:free",
                   "fallbacks": ["meta-llama/llama-3.3-70b-instruct:free",
                                 "mistralai/mistral-7b-instruct:free"]},
    "openai": {"base": "https://api.openai.com/v1", "model": "gpt-4o-mini", "fallbacks": []},
    "together": {"base": "https://api.together.xyz/v1",
                 "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free", "fallbacks": []},
}


def api_key() -> str:
    load_env()
    return (os.environ.get("AI_API_KEY") or "").strip()


def ai_config(cfg: dict | None = None) -> dict:
    return (cfg or load_config()).get("ai", {}) or {}


def ai_enabled(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    return bool(ai_config(cfg).get("enabled")) and bool(api_key())


def _resolve(cfg: dict) -> tuple[str, str, list[str]]:
    a = ai_config(cfg)
    provider = (a.get("provider") or "groq").lower()
    preset = PROVIDERS.get(provider, PROVIDERS["groq"])
    base = (a.get("base_url") or preset["base"]).rstrip("/")
    model = a.get("model") or preset["model"]
    fallbacks = a.get("fallback_models") or preset["fallbacks"]
    return base, model, [m for m in ([model] + fallbacks) if m]


def complete(system: str, user: str, cfg: dict | None = None,
             json_mode: bool = False, max_tokens: int = 900, temperature: float = 0.6) -> str | None:
    """Return the assistant text (or None on any failure). Tries each model in
    turn so a throttled free model rolls to the next."""
    cfg = cfg or load_config()
    key = api_key()
    if not key:
        return None
    base, _, models = _resolve(cfg)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "HTTP-Referer": "https://github.com/muhammadroohullah110/client-hunter",
               "X-Title": "TDSOCH"}
    for model in models:
        body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            req = urllib.request.Request(f"{base}/chat/completions",
                                         data=json.dumps(body).encode(), headers=headers)
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
            text = data["choices"][0]["message"]["content"].strip()
            if text:
                return text
        except Exception as e:
            log.warning("AI model %s failed: %s", model, str(e)[:120])
            continue
    return None


def complete_json(system: str, user: str, cfg: dict | None = None, max_tokens: int = 900) -> dict | None:
    """Like complete() but parses JSON (tolerating ```json fences / prose wrap)."""
    raw = complete(system, user, cfg, json_mode=True, max_tokens=max_tokens, temperature=0.4)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].lstrip("json").strip() if "```" in raw[3:] else raw.strip("`")
    try:
        return json.loads(raw)
    except Exception:
        # fall back to the outermost {...}
        import re
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def test_key(cfg: dict | None = None) -> dict:
    """Quick connectivity check for the Settings page."""
    if not api_key():
        return {"ok": False, "msg": "No API key set (add one and save)."}
    out = complete("You are a test.", "Reply with the single word: OK", cfg, max_tokens=5)
    if out and "ok" in out.lower():
        base, model, _ = _resolve(cfg or load_config())
        return {"ok": True, "msg": f"Connected via {model}."}
    return {"ok": False, "msg": "Key set but the provider did not respond (check provider/model/key)."}
