"""Unit tests for Job identity + normalization helpers."""
from __future__ import annotations

from sources.base import Job, clean_text, make_id, safe_str, source_enabled


def _job(**kw) -> Job:
    defaults = dict(
        id="ignored", title="HRBP", company="Acme Corp",
        location="Bengaluru", country="India", url="https://x/1",
    )
    defaults.update(kw)
    return Job(**defaults)


def test_dedupe_key_matches_across_case_and_punctuation():
    a = _job(title="HR Business Partner!", company="Acme, Inc.")
    b = _job(title="hr business partner", company="acme inc")
    assert a.dedupe_key() == b.dedupe_key()


def test_dedupe_key_differs_across_countries():
    a = _job(country="India")
    b = _job(country="Qatar")
    assert a.dedupe_key() != b.dedupe_key()


def test_make_id_is_stable():
    assert make_id("Adzuna", "12345", "https://x") == make_id("Adzuna", "12345", "https://x")


def test_make_id_prefixed_with_source():
    assert make_id("Adzuna", "12345", "https://x").startswith("adzuna:")


def test_clean_text_strips_html_and_collapses_whitespace():
    assert clean_text("<p>Hello&nbsp;<b>world</b>\n\n!</p>") == "Hello world !"


def test_safe_str_handles_nan_and_none():
    assert safe_str(None) == ""
    assert safe_str(float("nan")) == ""
    assert safe_str(42) == "42"


def test_source_enabled_reads_nested_flag():
    cfg = {"sources": {"adzuna": {"enabled": True}, "jooble": {"enabled": False}}}
    assert source_enabled(cfg, "adzuna") is True
    assert source_enabled(cfg, "jooble") is False
    assert source_enabled(cfg, "missing") is False
    assert source_enabled({}, "adzuna") is False
