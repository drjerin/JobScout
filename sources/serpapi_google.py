"""SerpApi Google Jobs adapter (OPTIONAL): compliant proxy for LinkedIn/Naukri/Bayt.

Free tier is 250 searches/month, so this is off by default and self-limited via
config ``max_searches_per_run``. Get a key at https://serpapi.com/ and set
``SERPAPI_KEY`` in ``.env``.
"""
from __future__ import annotations

import os

import http_client
import logs
from sources.base import Job, clean_text, make_id, safe_str

_log = logs.get("scout.serpapi")
_ENDPOINT = "https://serpapi.com/search.json"


def fetch(country: str, ccfg: dict, cfg: dict) -> list[Job]:
    sc = (cfg.get("sources", {}) or {}).get("serpapi_google", {}) or {}
    if not sc.get("enabled"):
        return []
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        _log.info("SERPAPI_KEY not set; skipping")
        return []

    terms = cfg.get("search_terms", []) or []
    budget = int(sc.get("max_searches_per_run", 4))
    location = (ccfg.get("locations") or [country])[0]
    s = http_client.session()

    jobs: list[Job] = []
    for term in terms[:budget]:
        params = {
            "engine": "google_jobs",
            "q": f"{term} {country}",
            "location": location,
            "api_key": key,
        }
        try:
            resp = s.get(_ENDPOINT, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001 - isolate a misbehaving source
            _log.warning("%s/'%s' failed: %s", country, term, e)
            continue
        for r in data.get("jobs_results", []) or []:
            apply_opts = r.get("apply_options") or []
            link = safe_str(apply_opts[0].get("link")) if apply_opts else safe_str(r.get("share_link"))
            ext = r.get("detected_extensions") or {}
            jobs.append(Job(
                id=make_id("Google", r.get("job_id") or link, link),
                title=safe_str(r.get("title")),
                company=safe_str(r.get("company_name")),
                location=safe_str(r.get("location")) or location,
                country=country,
                url=link,
                description=clean_text(r.get("description")),
                source="Google",
                salary=safe_str(ext.get("salary")),
                posted=safe_str(ext.get("posted_at")),
            ))
    _log.info("%s: %d raw rows (used <= %d searches)", country, len(jobs), budget)
    return jobs
