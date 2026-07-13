"""Shared ``requests`` session with retries and backoff.

All HTTP-based source adapters use :func:`session` so a flaky upstream
(429s, 5xx from a free tier, transient DNS) doesn't kill a whole run.
"""
from __future__ import annotations

import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_lock = threading.Lock()
_session: requests.Session | None = None

_RETRY = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=0.6,
    status_forcelist=(408, 425, 429, 500, 502, 503, 504),
    allowed_methods=frozenset(("GET", "POST", "HEAD")),
    raise_on_status=False,
    respect_retry_after_header=True,
)


def session() -> requests.Session:
    """Return a process-wide session with retry/backoff configured."""
    global _session
    with _lock:
        if _session is None:
            s = requests.Session()
            adapter = HTTPAdapter(max_retries=_RETRY, pool_connections=10, pool_maxsize=10)
            s.mount("http://", adapter)
            s.mount("https://", adapter)
            s.headers.update({"User-Agent": "job-scout/1.0 (+local)"})
            _session = s
        return _session
