"""Transparent match scoring: resume similarity + a matching checklist.

No machine learning. Every number is explainable and shown in the email.

    match% = resume_weight * resume_similarity%  +  matching_weight * checklist%
"""
from __future__ import annotations

import re

from sources.base import Job

# Match "N years" or "N-M years" ONLY when it's clearly experience-related.
# We look for a keyword within ~30 chars before or after: experience / exp / of.
_EXP_KW = r"(?:experience|experienc(?:ed|e)|exp\.?|yrs?\s+of|years?\s+of)"
_YEARS_RE = re.compile(
    r"(?P<n>\d{1,2})\s*\+?\s*(?:-\s*(?P<m>\d{1,2})\s*)?year",
    re.I,
)


# ── semantic-similarity calibration ────────────────────────────────────────
def similarity_to_percent(cos: float, cfg: dict) -> float:
    s = cfg.get("similarity", {}) or {}
    floor = float(s.get("sim_floor", 0.20))
    ceil = float(s.get("sim_ceiling", 0.80))
    if ceil <= floor:
        ceil = floor + 1e-6
    pct = (cos - floor) / (ceil - floor)
    return max(0.0, min(1.0, pct)) * 100.0


# ── hard filters ───────────────────────────────────────────────────────────
def passes_dealbreakers(job: Job, req: dict):
    """Return ``(ok, reason)``. A False result drops the job entirely."""
    allowed = [c.lower() for c in (req.get("allowed_countries") or [])]
    if allowed and job.country.lower() not in allowed:
        return False, f"country {job.country} not allowed"

    title_l = job.title.lower()
    for bad in req.get("exclude_titles") or []:
        if bad.lower() in title_l:
            return False, f"excluded title keyword '{bad}'"

    text_l = f"{job.title} {job.description}".lower()
    for bad in req.get("exclude_keywords") or []:
        if bad.lower() in text_l:
            return False, f"excluded keyword '{bad}'"

    comp_l = job.company.lower()
    for bad in req.get("exclude_companies") or []:
        if bad and bad.lower() in comp_l:
            return False, f"excluded company '{bad}'"

    return True, ""


def _extract_years(text: str) -> int | None:
    """Best-effort extraction of the required-experience number.

    Only considers "N years" mentions that appear near an experience keyword.
    Prefers the smallest such number (the minimum requirement in a range).
    Returns ``None`` when no experience-anchored mention is found.
    """
    if not text:
        return None
    text_l = text.lower()
    yrs: list[int] = []
    for m in _YEARS_RE.finditer(text_l):
        start, end = m.span()
        window = text_l[max(0, start - 32): min(len(text_l), end + 32)]
        if re.search(_EXP_KW, window):
            yrs.append(int(m.group("n")))
    return min(yrs) if yrs else None


# ── matching checklist ─────────────────────────────────────────────────────
def requirements_score(job: Job, req: dict):
    """Return ``(score_0_100, notes)`` where notes is a list of ``(status, label)``."""
    notes: list[tuple[str, str]] = []
    text_l = f"{job.title}\n{job.description}".lower()
    title_l = job.title.lower()

    # 1) Target title (40 pts) — strongest signal for a focused search.
    targets = req.get("target_titles") or []
    hit_title = next((t for t in targets if t.lower() in title_l), None)
    if hit_title:
        title_pts = 40.0
        notes.append(("ok", hit_title))
    else:
        body_hit = any(t.lower() in text_l for t in targets)
        title_pts = 15.0 if body_hit else 0.0
        notes.append(("warn" if body_hit else "bad", "title off-target"))

    # 2) Must-have skills (35 pts), scaled by fraction present.
    musts = req.get("must_have_skills") or []
    present = [s for s in musts if s.lower() in text_l]
    must_pts = (len(present) / len(musts) * 35.0) if musts else 35.0
    if musts:
        if present:
            notes.append(("ok", f"{len(present)}/{len(musts)} must-haves"))
        else:
            notes.append(("bad", "no must-haves"))

    # 3) Seniority (15 pts).
    band = req.get("seniority") or {}
    lo, hi = band.get("min_years"), band.get("max_years")
    years = _extract_years(text_l)
    if years is None:
        sen_pts = 10.0
        notes.append(("warn", "exp n/a"))
    elif (lo is None or years >= lo) and (hi is None or years <= hi):
        sen_pts = 15.0
        notes.append(("ok", f"{years}+ yrs"))
    else:
        sen_pts = 4.0
        notes.append(("warn", f"{years} yrs off-band"))

    # 4) Nice-to-haves (10 pts), scaled by fraction present.
    nice = req.get("nice_to_have_skills") or []
    nice_present = [s for s in nice if s.lower() in text_l]
    nice_pts = (len(nice_present) / len(nice) * 10.0) if nice else 0.0

    # 5) Salary floor — informational note only (never drops a job).
    floor = req.get("salary_floor") or 0
    if floor:
        nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]{4,}", job.salary or "")]
        if not nums:
            notes.append(("warn", "salary n/a"))
        elif max(nums) >= floor:
            notes.append(("ok", "salary ok"))
        else:
            notes.append(("warn", "salary low"))

    score = title_pts + must_pts + sen_pts + nice_pts
    return max(0.0, min(100.0, score)), notes


def final_percent(sim_pct: float, req_pct: float, cfg: dict) -> float:
    w = cfg.get("weights", {}) or {}
    rw = float(w.get("resume_weight", 0.5))
    # Prefer "matching_weight" (new); fall back to legacy "requirements_weight".
    qw = float(w.get("matching_weight", w.get("requirements_weight", 0.5)))
    tot = (rw + qw) or 1.0
    return (rw * sim_pct + qw * req_pct) / tot
