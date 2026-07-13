"""Unit tests for the transparent scoring layer."""
from __future__ import annotations

from score import (
    _extract_years,
    final_percent,
    passes_dealbreakers,
    requirements_score,
    similarity_to_percent,
)
from sources.base import Job


def _job(**kw) -> Job:
    defaults = dict(
        id="test:1", title="HR Business Partner", company="Acme",
        location="Bengaluru", country="India",
        url="https://x", description="", source="Indeed",
    )
    defaults.update(kw)
    return Job(**defaults)


# ── similarity_to_percent ─────────────────────────────────────────────────
def test_similarity_below_floor_clamps_to_zero():
    assert similarity_to_percent(0.05, {"similarity": {"sim_floor": 0.2, "sim_ceiling": 0.8}}) == 0.0


def test_similarity_above_ceiling_clamps_to_hundred():
    assert similarity_to_percent(0.95, {"similarity": {"sim_floor": 0.2, "sim_ceiling": 0.8}}) == 100.0


def test_similarity_mid_range():
    pct = similarity_to_percent(0.5, {"similarity": {"sim_floor": 0.2, "sim_ceiling": 0.8}})
    assert 49.9 <= pct <= 50.1


def test_similarity_handles_degenerate_range():
    # ceil<=floor must not divide by zero.
    similarity_to_percent(0.5, {"similarity": {"sim_floor": 0.5, "sim_ceiling": 0.5}})


# ── _extract_years (experience-anchored) ──────────────────────────────────
def test_extract_years_anchored_on_experience():
    assert _extract_years("5+ years of experience required") == 5


def test_extract_years_ignores_unrelated_year_mentions():
    # A "5-year strategic plan" should NOT count as experience.
    assert _extract_years("Own the 5-year strategic plan for the region.") is None


def test_extract_years_picks_minimum_in_range():
    assert _extract_years("4-8 years of experience in HR") == 4


def test_extract_years_returns_none_for_empty():
    assert _extract_years("") is None
    assert _extract_years("no numbers at all") is None


# ── passes_dealbreakers ───────────────────────────────────────────────────
def test_dealbreaker_country_not_allowed():
    ok, reason = passes_dealbreakers(_job(country="Germany"), {"allowed_countries": ["India", "Qatar"]})
    assert not ok and "country" in reason


def test_dealbreaker_excluded_title():
    ok, _ = passes_dealbreakers(_job(title="HR Intern"), {"exclude_titles": ["intern"]})
    assert not ok


def test_dealbreaker_excluded_company_case_insensitive():
    ok, _ = passes_dealbreakers(_job(company="BadCo Ltd."), {"exclude_companies": ["badco"]})
    assert not ok


def test_dealbreaker_no_rules_passes():
    ok, _ = passes_dealbreakers(_job(), {})
    assert ok


# ── requirements_score ────────────────────────────────────────────────────
def test_requirements_perfect_title_match():
    req = {"target_titles": ["HR Business Partner"], "must_have_skills": []}
    score, notes = requirements_score(_job(), req)
    assert score >= 40  # title alone is 40 pts


def test_requirements_off_target_title_still_scores_low():
    # With target-title miss, missing must-haves, and no experience mentioned,
    # the score should sit far below a perfect 100.
    req = {
        "target_titles": ["Engineer"],
        "must_have_skills": ["python", "kubernetes"],
    }
    score, notes = requirements_score(_job(title="Random role"), req)
    assert score < 40
    assert any("off-target" in label for _st, label in notes)


# ── final_percent ─────────────────────────────────────────────────────────
def test_final_percent_uses_new_weight_name():
    cfg = {"weights": {"resume_weight": 0.4, "matching_weight": 0.6}}
    assert final_percent(50, 100, cfg) == 50 * 0.4 + 100 * 0.6


def test_final_percent_falls_back_to_legacy_name():
    cfg = {"weights": {"resume_weight": 0.4, "requirements_weight": 0.6}}
    assert final_percent(50, 100, cfg) == 50 * 0.4 + 100 * 0.6
