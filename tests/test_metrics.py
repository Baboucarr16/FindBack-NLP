"""Metric-correctness tests for src/benchmark_evaluate.py.

Tiny hand-built fixtures with hand-computed expectations. These verify
code correctness only and are explicitly synthetic.
"""

import math

import pandas as pd
import pytest

import tests.conftest  # noqa: F401  (path setup)
from benchmark_evaluate import evaluate_method, ndcg_at_k


def _frames():
    lost = pd.DataFrame([{
        "report_id": "L1", "report_type": "Lost", "item_category": "",
        "description": "query", "organization_type": "", "organization_name": "",
        "campus_or_branch": "", "building_or_terminal": "", "floor_or_level": "",
        "specific_area": "", "date": "", "approx_time": "", "status": "Lost",
    }])
    found = pd.DataFrame([{
        "report_id": fid, "report_type": "Found", "item_category": "",
        "description": f"candidate {fid}", "organization_type": "",
        "organization_name": "", "campus_or_branch": "",
        "building_or_terminal": "", "floor_or_level": "", "specific_area": "",
        "date": "", "approx_time": "", "status": "Found",
    } for fid in ("F1", "F2", "F3", "F4")])
    return lost, found


def _fixed_scores(values):
    def scorer(lost, found_df):
        return list(values)
    return scorer


def test_rank_two_gives_expected_metrics():
    lost, found = _frames()
    labels = pd.DataFrame([{"lost_id": "L1", "expected_found_id": "F3", "has_match": "1"}])
    # Empty context fields -> final score = desc * 0.5, so F3 (0.7) ranks 2nd.
    result = evaluate_method(lost, found, labels, _fixed_scores([0.9, 0.5, 0.7, 0.1]),
                             "tfidf", top_n=5, threshold=None)
    assert result["top1"] == 0.0
    assert result["top3"] == 1.0
    assert result["top5"] == 1.0
    assert result["mrr"] == 0.5
    assert result["ndcg"] == pytest.approx(1.0 / math.log2(3))


def test_ndcg_helper():
    assert ndcg_at_k(1, 5) == 1.0
    assert ndcg_at_k(2, 5) == 1.0 / math.log2(3)
    assert ndcg_at_k(6, 5) == 0.0
    assert ndcg_at_k(None, 5) == 0.0


def test_threshold_abstention_counts_as_miss():
    lost, found = _frames()
    labels = pd.DataFrame([{"lost_id": "L1", "expected_found_id": "F1", "has_match": "1"}])
    result = evaluate_method(lost, found, labels, _fixed_scores([0.9, 0.5, 0.7, 0.1]),
                             "tfidf", top_n=5, threshold=0.95)
    assert result["top1"] == 0.0  # top score 0.45 < 0.95 -> abstained
    assert result["details"][0]["abstained"] is True


def test_no_match_queries_excluded_from_ranking():
    lost, found = _frames()
    labels = pd.DataFrame([
        {"lost_id": "L1", "expected_found_id": "F1", "has_match": "1"},
        {"lost_id": "L1", "expected_found_id": "", "has_match": "0"},
    ])
    result = evaluate_method(lost, found, labels, _fixed_scores([0.9, 0.5, 0.7, 0.1]),
                             "tfidf", top_n=5, threshold=0.95)
    assert result["n_match"] == 1
    assert result["top1"] == 0.0  # the matching query abstained
    assert result["abstain_acc"] == 1.0  # the no-match query abstained correctly
