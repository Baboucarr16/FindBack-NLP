"""Unit tests for the pure scoring helpers in src/matcher.py.

Importing matcher reads the production CSV once (read-only) to build
its TF-IDF index; these tests never write to it.
"""

import tests.conftest  # noqa: F401  (path setup)
from matcher import (
    calculate_category_similarity,
    calculate_location_similarity,
    calculate_time_similarity,
)


def test_location_exact_match():
    report = {
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Central Library",
        "floor_or_level": "2nd Floor",
        "specific_area": "Reading Room",
    }
    assert calculate_location_similarity(report, dict(report)) == 1.0


def test_location_mismatch_is_low():
    lost = {
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Central Library",
        "floor_or_level": "2nd Floor",
        "specific_area": "Reading Room",
    }
    found = {
        "organization_name": "Metro International Airport",
        "campus_or_branch": "Terminal 2",
        "building_or_terminal": "Terminal 2",
        "floor_or_level": "Level 3",
        "specific_area": "Departure Hall",
    }
    assert calculate_location_similarity(lost, found) < 0.3


def test_location_missing_fields_not_penalized():
    lost = {"organization_name": "Greenfield University"}
    found = {"organization_name": "Greenfield University"}
    assert calculate_location_similarity(lost, found) == 1.0
    assert calculate_location_similarity({}, {}) == 0.0
    assert calculate_location_similarity(lost, {}) == 0.0


def test_time_close_and_far():
    lost = {"date": "2026-08-18", "approx_time": "16:20"}
    assert calculate_time_similarity(lost, {"date": "2026-08-18", "approx_time": "16:45"}) == 1.0
    assert calculate_time_similarity(lost, {"date": "2026-08-18", "approx_time": "17:10"}) == 0.8
    assert calculate_time_similarity(lost, {"date": "2026-08-20", "approx_time": "16:20"}) == 0.0


def test_time_missing_or_malformed_is_safe():
    lost = {"date": "2026-08-18", "approx_time": "16:20"}
    assert calculate_time_similarity(lost, {}) == 0.0
    assert calculate_time_similarity({}, lost) == 0.0
    assert calculate_time_similarity(lost, {"date": "not-a-date", "approx_time": "xx"}) == 0.0


def test_category_match_mismatch_missing():
    assert calculate_category_similarity({"item_category": "Phone"}, {"item_category": "phone"}) == 1.0
    assert calculate_category_similarity({"item_category": "Phone"}, {"item_category": "Wallet"}) == 0.0
    assert calculate_category_similarity({}, {"item_category": "Wallet"}) == 0.0
