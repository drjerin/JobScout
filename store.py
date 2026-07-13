"""SQLite job store shared by ``run.py`` (writes) and ``app.py`` (reads/updates).

Uses only the stdlib :mod:`sqlite3`. Doubles as the dedupe memory: an id
already in the table has been seen before, so it won't be emailed again. The
web UI reads this table to show current + past matches with a per-job status.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from sources.base import Job

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "jobs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    title         TEXT, company TEXT, location TEXT, country TEXT,
    url           TEXT, description TEXT, source TEXT, salary TEXT, posted TEXT,
    match_percent REAL,
    fit_notes     TEXT,          -- JSON list of [status, label]
    why           TEXT,
    status        TEXT DEFAULT 'new',   -- new | applied | hidden
    emailed       INTEGER DEFAULT 0,
    first_seen    TEXT, last_seen TEXT
);
CREATE INDEX IF NOT EXISTS idx_country ON jobs(country);
CREATE INDEX IF NOT EXISTS idx_status  ON jobs(status);
"""

VALID_STATUS = {"new", "applied", "hidden"}
_initialized = False


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables/indexes once per process."""
    global _initialized
    if _initialized:
        return
    with _conn() as c:
        c.executescript(_SCHEMA)
    _initialized = True


def seen_ids() -> set[str]:
    init_db()
    with _conn() as c:
        return {r["id"] for r in c.execute("SELECT id FROM jobs")}


def upsert_jobs(jobs: list[Job]) -> None:
    """Insert new jobs (status 'new'); refresh score/last_seen for existing ones."""
    init_db()
    if not jobs:
        return
    now = datetime.now().isoformat(timespec="seconds")
    rows = [
        (
            j.id, j.title, j.company, j.location, j.country, j.url,
            (j.description or "")[:2000], j.source, j.salary, j.posted,
            j.match_percent, json.dumps(j.fit_notes), j.why, now, now,
        )
        for j in jobs
    ]
    with _conn() as c:
        c.executemany(
            """
            INSERT INTO jobs
                (id,title,company,location,country,url,description,source,salary,
                 posted,match_percent,fit_notes,why,status,emailed,first_seen,last_seen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'new', 0, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_seen=excluded.last_seen,
                match_percent=excluded.match_percent,
                fit_notes=excluded.fit_notes,
                why=excluded.why
            """,
            rows,
        )


def mark_emailed(ids: list[str]) -> None:
    if not ids:
        return
    init_db()
    with _conn() as c:
        c.executemany("UPDATE jobs SET emailed=1 WHERE id=?", [(i,) for i in ids])


def set_status(job_id: str, status: str) -> bool:
    if status not in VALID_STATUS:
        return False
    init_db()
    with _conn() as c:
        c.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
    return True


def query(country: str | None = None, status: str = "new",
          search: str | None = None, sort: str = "match",
          limit: int = 500) -> list[dict]:
    init_db()
    sql = "SELECT * FROM jobs WHERE 1=1"
    args: list = []
    if country:
        sql += " AND country=?"
        args.append(country)
    if status and status != "all":
        sql += " AND status=?"
        args.append(status)
    if search:
        sql += " AND (lower(title) LIKE ? OR lower(company) LIKE ?)"
        s = f"%{search.lower()}%"
        args += [s, s]
    order = {
        "match": "match_percent DESC",
        "recent": "last_seen DESC",
        "company": "company COLLATE NOCASE ASC",
    }.get(sort, "match_percent DESC")
    sql += f" ORDER BY {order} LIMIT ?"
    args.append(limit)

    with _conn() as c:
        rows = [dict(r) for r in c.execute(sql, args)]
    for r in rows:
        try:
            r["fit_notes"] = json.loads(r["fit_notes"] or "[]")
        except (TypeError, ValueError):
            r["fit_notes"] = []
    return rows


def counts() -> dict[str, dict[str, int]]:
    """Return ``{country: {status: n}}`` plus an ``emailed`` tally for the UI header."""
    init_db()
    out: dict[str, dict[str, int]] = {}
    with _conn() as c:
        for r in c.execute(
            "SELECT country, status, COUNT(*) n FROM jobs GROUP BY country, status"
        ):
            out.setdefault(r["country"], {})[r["status"]] = r["n"]
    return out


def prune(days: int = 30) -> int:
    """Delete stale 'new'/'hidden' jobs; keep everything the user marked 'applied'."""
    init_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM jobs WHERE status IN ('new','hidden') AND last_seen < ?",
            (cutoff,),
        )
        return cur.rowcount
