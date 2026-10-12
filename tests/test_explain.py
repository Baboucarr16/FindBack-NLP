"""Tests for src/explain.py (synthetic fixtures only)."""

import tests.conftest  # noqa: F401  (path setup)
from explain import WEIGHTS, explain_match


def _lost(**overrides):
    report = {
        "report_id": "L1",
        "item_category": "Backpack",
        "description": "lost navy backpack with nike logo",
        "organization_type": "University",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Central Library",
        "floor_or_level": "2nd Floor",
        "specific_area": "Reading Room",
        "date": "2026-08-18",
        "approx_time": "16:20",
    }
    report.update(overrides)
    return report


def _found(**overrides):
    record = {
        "report_id": "F1",
        "item_category": "Backpack",
        "description": "found dark blue bag with nike mark",
        "organization_type": "University",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Central Library",
        "floor_or_level": "2nd Floor",
        "specific_area": "Reading Room",
        "date": "2026-08-18",
        "approx_time": "16:45",
        "semantic_score": 0.85,
        "location_score": 1.0,
        "time_score": 1.0,
        "category_score": 1.0,
        "final_score": 0.9,
    }
    record.update(overrides)
    return record


def test_weights_match_live_matcher():
    assert [(key, weight) for key, _, weight, _ in WEIGHTS] == [
        ("semantic", 0.50),
        ("location", 0.25),
        ("time", 0.15),
        ("category", 0.10),
    ]


def test_strong_match_reports_supporting_evidence():
    explanation = explain_match(_lost(), _found())
    assert len(explanation["supporting"]) >= 5  # category + 5 location + time + text
    assert explanation["conflicting"] == []
    labels = [item["label"] for item in explanation["contributions"]]
    assert labels == ["Description", "Location", "Time", "Category"]
    points = sum(item["points"] for item in explanation["contributions"])
    assert abs(points - 0.85 * 0.50 - 1.0 * 0.25 - 1.0 * 0.15 - 1.0 * 0.10) < 1e-9


def test_conflicts_are_reported_honestly():
    explanation = explain_match(
        _lost(),
        _found(item_category="Wallet",
               organization_name="Metro International Airport",
               date="2026-08-25", approx_time="09:00",
               semantic_score=0.2),
    )
    text = " ".join(explanation["conflicting"])
    assert "Different category" in text
    assert "Different place" in text
    assert "days apart" in text
    assert "low similarity" in text


def test_missing_attributes_produce_no_statements():
    explanation = explain_match({}, {})
    assert explanation["supporting"] == []
    assert explanation["conflicting"] == []
    assert explanation["contributions"][0]["score"] == 0.0


def test_scores_never_described_as_probabilities():
    explanation = explain_match(_lost(), _found())
    for point in explanation["supporting"] + explanation["conflicting"]:
        assert "probab" not in point.lower()
    assert "not a probability" in explanation["summary"]


def test_malformed_scores_are_safe():
    record = _found(semantic_score="nonsense", final_score=None)
    del record["location_score"]
    explanation = explain_match(_lost(), record)
    assert explanation["contributions"][0]["score"] == 0.0
    assert explanation["contributions"][1]["score"] == 0.0
