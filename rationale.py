"""Optional one-line "why it fits" per top job, via Groq's free API.

Silently no-ops if ``GROQ_API_KEY`` is unset or a call fails — the digest is
fully useful without it. Only the top rows per country are annotated to stay
well within free limits.
"""
from __future__ import annotations

import os
import time

import http_client
import logs

_log = logs.get("scout.rationale")
_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.3-70b-versatile"


def add_rationales(jobs, resume_snippet: str = "", per_country_top: int = 5) -> None:
    """Mutate up to ``per_country_top`` jobs in place, setting ``job.why``."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or not jobs:
        return
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    s = http_client.session()
    consecutive_failures = 0
    for job in jobs[:per_country_top]:
        prompt = (
            "In 15 words or fewer, say why this role is or isn't a strong fit for "
            "the candidate. Be specific and concrete.\n\n"
            f"ROLE: {job.title} at {job.company} ({job.location}).\n"
            f"DESCRIPTION: {(job.description or '')[:700]}\n"
            f"CANDIDATE (resume excerpt): {resume_snippet[:400]}"
        )
        why = _call_once(s, headers, prompt)
        if why is None:
            # One backoff-retry so a transient blip doesn't nuke all rationales.
            time.sleep(1.5)
            why = _call_once(s, headers, prompt)
        if why is None:
            consecutive_failures += 1
            if consecutive_failures >= 2:
                _log.warning("rationale disabled for this run after repeated failures")
                return
            continue
        consecutive_failures = 0
        job.why = why


def _call_once(session, headers: dict, prompt: str) -> str | None:
    try:
        resp = session.post(
            _ENDPOINT,
            headers=headers,
            json={
                "model": _MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 40,
                "temperature": 0.3,
            },
            timeout=25,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001 - rationale is best-effort
        _log.info("rationale call failed: %s", e)
        return None
