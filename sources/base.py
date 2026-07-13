"""Shared job model and normalization helpers used by every source adapter."""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    country: str            # the country key from config.yaml
    url: str                # apply / redirect link
    description: str = ""
    source: str = ""        # LinkedIn | Indeed | Naukri | Bayt | Jooble | Adzuna | Google
    salary: str = ""
    posted: str = ""        # human-ish string, e.g. "2 days ago" or a date

    # filled in later by the scorer:
    match_percent: float = 0.0
    fit_notes: list[tuple[str, str]] = field(default_factory=list)  # (status, label); status in {ok,warn,bad}
    why: str = ""                                                   # optional one-line rationale

    def dedupe_key(self) -> str:
        """Cross-source identity.

        Uses title + company + country so a company posting the same role in
        two cities keeps both openings. Location isn't included because
        sources normalize it inconsistently (city vs. metro vs. remote).
        """
        return f"{_norm(self.title)}|{_norm(self.company)}|{_norm(self.country)}"

    def match_text(self) -> str:
        """Text fed to the embedder for resume matching."""
        return "\n".join(p for p in [self.title, self.company, self.description] if p)


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def make_id(source: str, native_id, url: str) -> str:
    """Stable unique id for dedupe / seen tracking."""
    basis = str(native_id) if native_id else (url or "")
    h = hashlib.sha1(f"{source}:{basis}".encode()).hexdigest()[:16]
    return f"{source.lower()}:{h}"


def clean_text(s) -> str:
    """Strip HTML tags and collapse whitespace (several sources return HTML)."""
    if not s:
        return ""
    s = str(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;?", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def safe_str(v) -> str:
    """Coerce arbitrary values (incl. pandas NaN) to a clean string."""
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v).strip()


def source_enabled(cfg: dict, key: str) -> bool:
    """Return True iff ``cfg['sources'][key]['enabled']`` is truthy."""
    return bool(((cfg.get("sources", {}) or {}).get(key, {}) or {}).get("enabled"))
