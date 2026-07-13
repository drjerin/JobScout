"""Adzuna adapter: free official API.

Instant free credentials at https://developer.adzuna.com/ — set ``ADZUNA_APP_ID``
and ``ADZUNA_APP_KEY`` in ``.env``. Descriptions are snippet-length (full text
lives behind ``redirect_url``, which becomes the apply link).
"""
from __future__ import annotations

import math
import os

import http_client
import logs
from sources.base import Job, clean_text, make_id, safe_str, source_enabled

_log = logs.get("scout.adzuna")
_ENDPOINT = "https://api.adzuna.com/v1/api/jobs/{cc}/search/1"


def fetch(country: str, ccfg: dict, cfg: dict) -> list[Job]:
    if not source_enabled(cfg, "adzuna"):
        return []
    cc = ccfg.get("adzuna_country")
    if not cc:
        return []  # country not covered by Adzuna
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if not (app_id and app_key):
        _log.info("ADZUNA_APP_ID/ADZUNA_APP_KEY not set; skipping")
        return []

    terms = cfg.get("search_terms", []) or []
    locations = ccfg.get("locations") or [country]
    max_days = max(1, math.ceil(int(cfg.get("hours_old", 72)) / 24))
    url = _ENDPOINT.format(cc=cc)
    s = http_client.session()

    jobs: list[Job] = []
    for term in terms:
        for loc in locations:
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": term,
                "where": loc,
                "results_per_page": 20,
                "max_days_old": max_days,
                "content-type": "application/json",
            }
            try:
                resp = s.get(url, params=params, timeout=25)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:  # noqa: BLE001 - isolate a misbehaving source
                _log.warning("%s/'%s'@%s failed: %s", country, term, loc, e)
                continue
            for r in data.get("results", []) or []:
                link = safe_str(r.get("redirect_url"))
                jobs.append(Job(
                    id=make_id("Adzuna", r.get("id") or link, link),
                    title=safe_str(r.get("title")),
                    company=safe_str((r.get("company") or {}).get("display_name")),
                    location=safe_str((r.get("location") or {}).get("display_name")) or loc,
                    country=country,
                    url=link,
                    description=clean_text(r.get("description")),
                    source="Adzuna",
                    salary=_salary(r),
                    posted=safe_str(r.get("created")),
                ))
    _log.info("%s: %d raw rows", country, len(jobs))
    return jobs


def _salary(r: dict) -> str:
    mn, mx = r.get("salary_min"), r.get("salary_max")
    parts = [str(int(x)) for x in (mn, mx) if isinstance(x, (int, float))]
    return "-".join(parts) if parts else ""
