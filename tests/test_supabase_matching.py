"""Offline regression coverage for matching database report rows."""

import numpy as np

import tests.conftest  # noqa: F401
import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "semantic_matcher.py"
_SPEC = importlib.util.spec_from_file_location("semantic_matcher_real", _MODULE_PATH)
semantic_matcher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(semantic_matcher)


def test_supabase_report_rows_use_existing_score_weights(monkeypatch):
    class Model:
        def encode(self, descriptions, normalize_embeddings=False):
            assert normalize_embeddings is True
            return np.tile(np.array([[1.0, 0.0]]), (len(descriptions), 1))

    monkeypatch.setattr(semantic_matcher, "_get_model", lambda: Model())
    lost = {
        "description": "navy backpack",
        "item_category": "Backpack",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main",
        "building_or_terminal": "Library",
        "floor_or_level": "2",
        "specific_area": "Reading room",
        "date": "2026-08-18",
        "approx_time": "16:20",
    }
    found = {
        "id": "found-uuid",
        "legacy_report_id": "FB900",
        "report_type": "Found",
        "status": "active",
        "description": "navy backpack",
        "item_category": "Backpack",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main",
        "building_or_terminal": "Library",
        "floor_or_level": "2",
        "specific_area": "Reading room",
        "event_date": "2026-08-18",
        "approx_time": "16:20",
    }
    result = semantic_matcher.find_semantic_matches_against_reports(
        lost, [found], top_n=5)
    assert result.iloc[0]["id"] == "found-uuid"
    assert result.iloc[0]["report_id"] == "FB900"
    assert result.iloc[0]["final_score"] == 1.0
