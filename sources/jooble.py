"""Jooble adapter: free aggregator API with broad country coverage.

One key, POST keyword + location. Descriptions are snippet-length. Get a free
key at https://jooble.org/api/about and set ``JOOBLE_KEY`` in ``.env``.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import http_client
import logs
from sources.base import Job, clean_text, make_id, safe_str, source_enabled

_log = logs.get("scout.jooble")
_ENDPOINT = "https://jooble.org/api/{key}"

# Jooble sometimes returns 'updated' as ISO, sometimes as "N days ago".
_REL_RE = re.compile(r"(\d+)\s*(hour|day|week|month)s?\s*ago", re.I)


def fetch(country: str, ccfg: dict, cfg: dict) -> list[Job]:
    if not source_enabled(cfg, "jooble"):
        return []
    key = os.getenv("JOOBLE_KEY", "").strip()
    if not key:
        _log.info("JOOBLE_KEY not set; skipping")
        return []

    url = _ENDPOINT.format(key=key)
    terms = cfg.get("search_terms", []) or []
    locations = ccfg.get("locations") or [country]
    hours_old = int(cfg.get("hours_old", 72))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    s = http_client.session()

    jobs: list[Job] = []
    filtered = 0
    for term in terms:
        for loc in locations:
            try:
                resp = s.post(
                    url, json={"keywords": term, "location": loc}, timeout=25
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:  # noqa: BLE001 - isolate a misbehaving source
                _log.warning("%s/'%s'@%s failed: %s", country, term, loc, e)
                continue
            for j in data.get("jobs", []) or []:
                updated = safe_str(j.get("updated"))
                if updated and not _is_recent(updated, cutoff):
                    filtered += 1
                    continue
                link = safe_str(j.get("link"))
                jobs.append(Job(
                    id=make_id("Jooble", j.get("id") or link, link),
                    title=safe_str(j.get("title")),
                    company=safe_str(j.get("company")),
                    location=safe_str(j.get("location")) or loc,
                    country=country,
                    url=link,
                    description=clean_text(j.get("snippet")),
                    source="Jooble",
                    salary=safe_str(j.get("salary")),
                    posted=updated,
                ))
    _log.info("%s: %d raw rows (%d filtered by hours_old=%d)",
              country, len(jobs), filtered, hours_old)
    return jobs


def _is_recent(when: str, cutoff: datetime) -> bool:
    """Best-effort: return True unless we can prove the job is older than cutoff."""
    m = _REL_RE.search(when)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=n * 30),
        }[unit]
        return datetime.now(timezone.utc) - delta >= cutoff
    try:
        dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except ValueError:
        return True  # unknown format — don't drop
