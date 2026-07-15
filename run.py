#!/usr/bin/env python3
"""Job Scout — orchestrator.

Every run:  fetch -> dedupe -> filter -> embed -> score -> split by country ->
store -> optional rationale -> email one table per country -> remember.

Usage (CLI):
    python run.py             # fetch, score, store, and EMAIL the digest
    python run.py --no-email  # same but skip the email (used by the web UI)
    python run.py --dry-run   # fetch/score only; write digest_preview.html

Programmatic:
    from run import run_once
    summary = run_once(dry_run=False, no_email=True)
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

import email_report
import logs
import rationale
import resume_loader
import store
from embed import cosine, embed
from score import (
    final_percent,
    passes_dealbreakers,
    requirements_score,
    similarity_to_percent,
)
from sources import adzuna, jobspy_source, jooble, serpapi_google
from sources.base import Job

ROOT = Path(__file__).resolve().parent
SOURCES = [jobspy_source, jooble, adzuna, serpapi_google]
_MAX_WORKERS = 6

log = logs.setup()


# ── config helpers ─────────────────────────────────────────────────────────
def load_yaml(name: str) -> dict:
    path = ROOT / name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def enabled_countries(cfg: dict) -> list[tuple[str, dict]]:
    """Return ``[(country, country_cfg), ...]`` for every enabled country."""
    out: list[tuple[str, dict]] = []
    for name, ccfg in (cfg.get("countries") or {}).items():
        if (ccfg or {}).get("enabled"):
            out.append((name, ccfg))
    return out


def section_label(country: str, ccfg: dict) -> str:
    """Return the display label for a country ('🇮🇳 India' if emoji is set)."""
    emoji = (ccfg or {}).get("emoji") or ""
    return f"{emoji} {country}".strip()


# ── pipeline ────────────────────────────────────────────────────────────────
def gather(cfg: dict) -> list[Job]:
    """Fan out (source, country) fetches across a thread pool."""
    tasks: list[tuple[object, str, dict]] = []
    for country, ccfg in enabled_countries(cfg):
        for src in SOURCES:
            tasks.append((src, country, ccfg))

    jobs: list[Job] = []
    if not tasks:
        return jobs
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(src.fetch, country, ccfg, cfg): (src, country)
            for src, country, ccfg in tasks
        }
        for fut in as_completed(futures):
            src, country = futures[fut]
            try:
                jobs.extend(fut.result())
            except Exception as e:  # noqa: BLE001 - isolate a misbehaving source
                log.warning("[%s] %s errored: %s", src.__name__, country, e)
    return jobs


def dedupe(jobs: list[Job], seen: set[str]) -> list[Job]:
    """Prefer the richest copy of a duplicate (longest description)."""
    jobs = sorted(jobs, key=lambda j: len(j.description or ""), reverse=True)
    by_id: dict[str, Job] = {}
    by_key: set[str] = set()
    unique: list[Job] = []
    for j in jobs:
        if not (j.url and j.title):
            continue
        if j.id in seen or j.id in by_id:
            continue
        key = j.dedupe_key()
        if key in by_key:
            continue
        by_id[j.id] = j
        by_key.add(key)
        unique.append(j)
    return unique


def score_all(jobs: list[Job], resume_text: str, req: dict, cfg: dict) -> list[Job]:
    survivors = [j for j in jobs if passes_dealbreakers(j, req)[0]]
    if not survivors:
        return []
    resume_vec = embed(resume_text)[0]
    vecs = embed([j.match_text() for j in survivors])
    sims = cosine(resume_vec, vecs)
    min_match = float(cfg.get("min_match_percent", 55))

    kept: list[Job] = []
    for j, cos in zip(survivors, sims, strict=False):
        sim_pct = similarity_to_percent(float(cos), cfg)
        req_pct, notes = requirements_score(j, req)
        j.match_percent = round(final_percent(sim_pct, req_pct, cfg), 1)
        j.fit_notes = notes
        if j.match_percent >= min_match:
            kept.append(j)
    return kept


def split_and_rank(jobs: list[Job], country: str, limit: int) -> list[Job]:
    subset = [j for j in jobs if j.country == country]
    subset.sort(key=lambda j: j.match_percent, reverse=True)
    return subset[:limit]


# ── main ─────────────────────────────────────────────────────────────────────
def run_once(dry_run: bool = False, no_email: bool = False) -> dict:
    """Run one pipeline iteration and return a summary dict.

    The scheduler, the web UI's "Run now" button and the CLI all call this.
    Errors inside sources are caught by ``gather()``; unexpected errors here
    propagate to the caller, which is expected to log them.
    """
    load_dotenv(ROOT / ".env")
    cfg = load_yaml("config.yaml")
    req = load_yaml("matching.yaml")
    resume_text = resume_loader.load(ROOT)

    profile = cfg.get("profile") or {}
    profile_name = profile.get("name") or "Job Scout"
    role = profile.get("role") or "role"

    seen = set() if dry_run else store.seen_ids()

    mode = "DRY-RUN" if dry_run else ("NO-EMAIL" if no_email else "LIVE")
    log.info("starting %s at %s", mode, datetime.now().strftime("%Y-%m-%d %H:%M"))

    raw = gather(cfg)
    log.info("%d raw rows fetched", len(raw))
    unique = dedupe(raw, seen)
    log.info("%d unique new jobs after dedupe", len(unique))
    scored = score_all(unique, resume_text, req, cfg)
    log.info("%d jobs at or above min_match_percent=%s",
             len(scored), cfg.get("min_match_percent"))

    rows = int(cfg.get("rows_per_table", 12))
    countries = enabled_countries(cfg)
    sections_data: list[tuple[str, str, list[Job]]] = []
    for name, ccfg in countries:
        top = split_and_rank(scored, name, rows)
        sections_data.append((name, section_label(name, ccfg), top))

    snippet = resume_text[:400]
    for _name, _label, top in sections_data:
        rationale.add_rationales(top, snippet)

    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    sections = [(label, top) for _name, label, top in sections_data]
    per_country_counts = "+".join(f"{len(top)} {name}" for name, _label, top in sections_data)
    total = sum(len(top) for _name, _label, top in sections_data)
    subject = f"{profile_name} · {role} · {per_country_counts} · {now}"
    meta = {
        "title": f"{profile_name} · {role}",
        "subtitle": f"{total} new matches • {now}",
    }

    summary = {
        "mode": mode,
        "raw": len(raw),
        "unique": len(unique),
        "scored": len(scored),
        "total_top": total,
        "per_country": per_country_counts,
        "emailed": False,
    }

    if dry_run:
        html = email_report.render_html(sections, meta)
        email_report.write_preview(html, str(ROOT / "digest_preview.html"))
        log.info("DRY-RUN complete — %s (no DB writes)", per_country_counts)
        return summary

    store.upsert_jobs(scored)
    store.prune(days=30)

    if no_email:
        log.info("NO-EMAIL complete — stored %d matches to the DB", len(scored))
        return summary

    if total:
        html = email_report.render_html(sections, meta)
        text = email_report.render_text(sections, meta)
        email_report.send_email(subject, html, text)
        emailed_ids: list[str] = []
        for _name, _label, top in sections_data:
            emailed_ids.extend(j.id for j in top)
        store.mark_emailed(emailed_ids)
        summary["emailed"] = True
        log.info("LIVE complete — emailed %s", per_country_counts)
    else:
        log.info("nothing new to email this run.")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Scout")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch/score only; write digest_preview.html, no DB or email")
    parser.add_argument("--no-email", action="store_true",
                        help="fetch, score and store to the DB, but do not send email")
    args = parser.parse_args()
    run_once(dry_run=args.dry_run, no_email=args.no_email)


if __name__ == "__main__":
    main()
