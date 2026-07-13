"""Unit tests for the SQLite store (uses a temp DB)."""
from __future__ import annotations

import importlib

import pytest

from sources.base import Job


def _make_job(id_="j:1", country="India", match=80.0) -> Job:
    return Job(
        id=id_, title="HR Business Partner", company="Acme",
        location="Bengaluru", country=country, url="https://x/1",
        description="Lead HR partnering.", source="Indeed",
        match_percent=match,
    )


@pytest.fixture()
def store_module(tmp_path, monkeypatch):
    """Reload the store module with DB_PATH pointing at a temp directory."""
    import store as _store

    monkeypatch.setattr(_store, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(_store, "_initialized", False)
    return importlib.reload(_store) if False else _store


def test_upsert_then_seen_ids(store_module):
    store_module.upsert_jobs([_make_job("j:1"), _make_job("j:2")])
    assert store_module.seen_ids() == {"j:1", "j:2"}


def test_upsert_updates_score_but_preserves_status(store_module):
    store_module.upsert_jobs([_make_job("j:1", match=60.0)])
    store_module.set_status("j:1", "applied")
    store_module.upsert_jobs([_make_job("j:1", match=90.0)])
    rows = store_module.query(status="applied")
    assert len(rows) == 1
    assert rows[0]["match_percent"] == 90.0
    assert rows[0]["status"] == "applied"


def test_set_status_rejects_invalid(store_module):
    store_module.upsert_jobs([_make_job("j:1")])
    assert store_module.set_status("j:1", "bogus") is False
    assert store_module.set_status("j:1", "hidden") is True


def test_query_filters_by_country_and_status(store_module):
    store_module.upsert_jobs([_make_job("j:1", country="India"), _make_job("j:2", country="Qatar")])
    store_module.set_status("j:1", "applied")
    assert len(store_module.query(country="India", status="applied")) == 1
    assert len(store_module.query(country="Qatar", status="new")) == 1
    assert len(store_module.query(country="Qatar", status="applied")) == 0


def test_counts_groups_by_country_and_status(store_module):
    store_module.upsert_jobs([
        _make_job("j:1", country="India"),
        _make_job("j:2", country="India"),
        _make_job("j:3", country="Qatar"),
    ])
    store_module.set_status("j:2", "applied")
    c = store_module.counts()
    assert c["India"]["new"] == 1
    assert c["India"]["applied"] == 1
    assert c["Qatar"]["new"] == 1
