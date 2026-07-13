"""JobSpy adapter: LinkedIn + Indeed + Naukri + Bayt (scraped from THIS machine).

Run on a laptop with a home/residential IP — cloud/datacenter IPs get blocked
within minutes. Naukri is used only for India-style regions, Bayt only for
Gulf regions. Each (site, term) call is isolated so one blocked source can't
kill the rest.
"""
from __future__ import annotations

import math

import logs
from sources.base import Job, clean_text, make_id, safe_str, source_enabled

_log = logs.get("scout.jobspy")

# Which JobSpy sites make sense per country. Countries not listed here get the
# generic set (indeed, linkedin, google) since those work almost everywhere.
_REGIONAL_SITES: dict[str, set[str]] = {
    "India": {"naukri"},
    "United Arab Emirates": {"bayt"},
    "UAE": {"bayt"},
    "Qatar": {"bayt"},
    "Saudi Arabia": {"bayt"},
    "Kuwait": {"bayt"},
    "Bahrain": {"bayt"},
    "Oman": {"bayt"},
}
_GLOBAL_SITES = {"indeed", "linkedin", "google", "glassdoor", "zip_recruiter"}

_LABEL = {
    "indeed": "Indeed", "linkedin": "LinkedIn", "naukri": "Naukri",
    "bayt": "Bayt", "google": "Google", "glassdoor": "Glassdoor",
    "zip_recruiter": "ZipRecruiter",
}


def _applicable(country: str) -> set[str]:
    return _GLOBAL_SITES | _REGIONAL_SITES.get(country, set())


def fetch(country: str, ccfg: dict, cfg: dict) -> list[Job]:
    sc = (cfg.get("sources", {}) or {}).get("jobspy", {}) or {}
    if not source_enabled(cfg, "jobspy"):
        return []
    try:
        from jobspy import scrape_jobs
    except ImportError:
        _log.warning("python-jobspy not installed; skipping (pip install -r requirements.txt)")
        return []

    allowed = _applicable(country)
    applicable = [s for s in (sc.get("sites") or []) if s in allowed]
    terms = cfg.get("search_terms", []) or []
    indeed_country = ccfg.get("indeed_country", country)
    hours_old = int(cfg.get("hours_old", 72))
    results_wanted = int(sc.get("results_wanted", 25))
    fetch_desc = bool(sc.get("linkedin_fetch_description", False))
    max_li = int(sc.get("max_linkedin_pages", 5))

    jobs: list[Job] = []
    for site in applicable:
        for term in terms:
            rw = min(results_wanted, max_li * 10) if site == "linkedin" else results_wanted
            try:
                df = scrape_jobs(
                    site_name=[site],
                    search_term=term,
                    location=country,               # country-level keeps volume/risk low
                    results_wanted=rw,
                    hours_old=hours_old,
                    country_indeed=indeed_country,
                    linkedin_fetch_description=(fetch_desc if site == "linkedin" else False),
                )
            except Exception as e:  # noqa: BLE001 - never let one site abort the run
                _log.warning("%s/%s/'%s' failed: %s", site, country, term, e)
                continue
            if df is None or len(df) == 0:
                continue
            for row in df.to_dict("records"):
                jobs.append(_row_to_job(row, site, country))

    _log.info("%s: %d raw rows from %s", country, len(jobs), applicable or [])
    return jobs


def _row_to_job(r: dict, site: str, country: str) -> Job:
    src = _LABEL.get(site, site.title())
    url = safe_str(r.get("job_url_direct")) or safe_str(r.get("job_url"))
    native = r.get("id") or url
    return Job(
        id=make_id(src, native, url),
        title=safe_str(r.get("title")),
        company=safe_str(r.get("company")),
        location=safe_str(r.get("location")) or country,
        country=country,
        url=url,
        description=clean_text(r.get("description")),
        source=src,
        salary=_salary(r),
        posted=safe_str(r.get("date_posted")),
    )


def _salary(r: dict) -> str:
    def _n(v):
        try:
            f = float(v)
            return None if math.isnan(f) else int(f)
        except (TypeError, ValueError):
            return None

    mn, mx = _n(r.get("min_amount")), _n(r.get("max_amount"))
    if not (mn or mx):
        return ""
    cur = safe_str(r.get("currency"))
    intv = safe_str(r.get("interval"))
    amount = "-".join(str(x) for x in (mn, mx) if x)
    return f"{cur} {amount} {intv}".strip()
