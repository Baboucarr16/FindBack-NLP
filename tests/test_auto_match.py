"""Tests for src/auto_match.py (synthetic fixtures, fake store)."""

import tests.conftest  # noqa: F401  (path setup)
from auto_match import (
    W_CAT,
    W_DESC,
    W_LOC,
    W_TIME,
    _time_score,
    default_score_fn,
    notify_min_score,
    process_new_found_report,
)


def _lost(lost_id="L1", **overrides):
    report = {
        "id": lost_id,
        "owner_id": "owner-1",
        "report_type": "Lost",
        "item_category": "Wallet",
        "description": "lost brown leather wallet",
        "organization_name": "Mall",
        "event_date": "2026-08-18",
        "approx_time": "13:10",
    }
    report.update(overrides)
    return report


class FakeStore:
    def __init__(self, lost, fail_on=None):
        self.lost = lost
        self.pairs = []
        self.notes = []
        self.fail_on = fail_on or set()

    def list_active_lost(self):
        if "list" in self.fail_on:
            raise RuntimeError("db down")
        return self.lost

    def upsert_match_result(self, pair):
        if "upsert" in self.fail_on:
            raise RuntimeError("db down")
        self.pairs.append(pair)
        return pair

    def create_notification(self, note):
        if "notify" in self.fail_on:
            raise RuntimeError("db down")
        if any(n["dedupe_key"] == note["dedupe_key"] for n in self.notes):
            return {"dedupe_key": note["dedupe_key"], "duplicate": True}
        self.notes.append(note)
        return note


def test_weights_match_live_matcher():
    assert (W_DESC, W_LOC, W_TIME, W_CAT) == (0.50, 0.25, 0.15, 0.10)


def test_default_scorer_rewards_same_item_and_venue():
    found = {"id": "F1", "item_category": "Wallet",
             "description": "found brown leather wallet",
             "organization_name": "Mall",
             "event_date": "2026-08-18", "approx_time": "13:35"}
    scores = default_score_fn([_lost()], found)
    assert scores["L1"]["final_score"] > 0.6
    assert scores["L1"]["category_score"] == 1.0


def test_default_scorer_penalizes_category_mismatch():
    found = {"id": "F1", "item_category": "Phone",
             "description": "found brown leather wallet",
             "organization_name": "Mall"}
    scores = default_score_fn([_lost()], found)
    assert scores["L1"]["category_score"] == 0.0


def test_time_buckets_match_live_matcher():
    base = {"event_date": "2026-08-18", "approx_time": "13:10"}
    assert _time_score(base, {"event_date": "2026-08-18",
                              "approx_time": "13:35"}) == 1.0
    assert _time_score(base, {"event_date": "2026-08-19",
                              "approx_time": "13:10"}) == 0.10
    assert _time_score(base, {}) == 0.0
    assert _time_score({}, base) == 0.0


def test_process_matches_above_cutoff_only():
    store = FakeStore([_lost("L1"), _lost("L2", owner_id="owner-2")])
    found = {"id": "F9", "item_category": "Wallet"}

    def scorer(lost_reports, found_report):
        return {"L1": {"semantic_score": 0.9, "location_score": 1.0,
                       "time_score": 1.0, "category_score": 1.0,
                       "final_score": 0.95},
                "L2": {"semantic_score": 0.1, "location_score": 0.0,
                       "time_score": 0.0, "category_score": 0.0,
                       "final_score": 0.05}}

    summary = process_new_found_report(found, store, score_fn=scorer,
                                       min_score=0.6)
    assert summary == {"matches": 1, "notifications": 1, "skipped": 0,
                       "errors": 0}
    assert store.pairs[0]["lost_report_id"] == "L1"
    assert store.pairs[0]["found_report_id"] == "F9"
    assert store.notes[0]["dedupe_key"] == "match:F9:L1"
    assert store.notes[0]["user_id"] == "owner-1"


def test_process_is_idempotent():
    store = FakeStore([_lost("L1")])
    found = {"id": "F9", "item_category": "Wallet"}

    def scorer(lost_reports, found_report):
        return {"L1": {"semantic_score": 1.0, "location_score": 1.0,
                       "time_score": 1.0, "category_score": 1.0,
                       "final_score": 1.0}}

    first = process_new_found_report(found, store, score_fn=scorer,
                                     min_score=0.6)
    second = process_new_found_report(found, store, score_fn=scorer,
                                      min_score=0.6)
    assert first["notifications"] == 1
    assert second["notifications"] == 0  # duplicate swallowed
    assert len(store.notes) == 1


def test_ownerless_match_creates_no_notification():
    store = FakeStore([_lost("L1", owner_id=None)])
    found = {"id": "F9", "item_category": "Wallet"}

    def scorer(lost_reports, found_report):
        return {"L1": {"semantic_score": 1.0, "location_score": 1.0,
                       "time_score": 1.0, "category_score": 1.0,
                       "final_score": 1.0}}

    summary = process_new_found_report(found, store, score_fn=scorer,
                                       min_score=0.6)
    assert summary == {"matches": 1, "notifications": 0, "skipped": 0,
                       "errors": 0}


def test_process_never_raises_and_counts_errors():
    assert process_new_found_report(
        {"id": "F9"}, FakeStore([], fail_on={"list"}),
        min_score=0.6) == {"matches": 0, "notifications": 0, "skipped": 0,
                           "errors": 0}

    def bad_scorer(lost_reports, found_report):
        raise RuntimeError("nlp down")

    assert process_new_found_report(
        {"id": "F9"}, FakeStore([_lost()]), score_fn=bad_scorer,
        min_score=0.6)["errors"] == 1

    summary = process_new_found_report(
        {"id": "F9"}, FakeStore([_lost()], fail_on={"upsert"}),
        score_fn=lambda lost, found: {
            "L1": {"semantic_score": 1.0, "location_score": 1.0,
                   "time_score": 1.0, "category_score": 1.0,
                   "final_score": 1.0}},
        min_score=0.6)
    assert summary == {"matches": 0, "notifications": 0, "skipped": 0,
                       "errors": 1}


def test_notify_fn_callable_path():
    store = FakeStore([_lost("L1")])
    found = {"id": "F9", "item_category": "Wallet"}
    calls = []

    def hook(lost, found_report, final):
        calls.append((lost["id"], found_report["id"], final))
        return {"id": "n1"}

    def scorer(lost_reports, found_report):
        return {"L1": {"semantic_score": 1.0, "location_score": 1.0,
                       "time_score": 1.0, "category_score": 1.0,
                       "final_score": 1.0}}

    summary = process_new_found_report(found, store, score_fn=scorer,
                                       min_score=0.6, notify_fn=hook)
    assert summary == {"matches": 1, "notifications": 1, "skipped": 0,
                       "errors": 0}
    assert calls == [("L1", "F9", 1.0)]
    assert store.notes == []  # store path untouched


def test_notify_fn_none_skips_and_counts():
    store = FakeStore([_lost("L1")])
    found = {"id": "F9", "item_category": "Wallet"}

    def scorer(lost_reports, found_report):
        return {"L1": {"semantic_score": 1.0, "location_score": 1.0,
                       "time_score": 1.0, "category_score": 1.0,
                       "final_score": 1.0}}

    summary = process_new_found_report(found, store, score_fn=scorer,
                                       min_score=0.6, notify_fn=None)
    assert summary == {"matches": 1, "notifications": 0, "skipped": 1,
                       "errors": 0}
    assert store.notes == []


def test_notify_fn_failure_counts_error():
    store = FakeStore([_lost("L1")])
    found = {"id": "F9", "item_category": "Wallet"}

    def boom(lost, found_report, final):
        raise RuntimeError("writer down")

    def scorer(lost_reports, found_report):
        return {"L1": {"semantic_score": 1.0, "location_score": 1.0,
                       "time_score": 1.0, "category_score": 1.0,
                       "final_score": 1.0}}

    summary = process_new_found_report(found, store, score_fn=scorer,
                                       min_score=0.6, notify_fn=boom)
    assert summary["errors"] == 1
    assert summary["notifications"] == 0


def test_notify_cutoff_configurable(monkeypatch):
    monkeypatch.setenv("FINDBACK_NOTIFY_MIN_SCORE", "0.9")
    assert notify_min_score() == 0.9
    monkeypatch.setenv("FINDBACK_NOTIFY_MIN_SCORE", "nonsense")
    assert notify_min_score() == 0.6
    monkeypatch.delenv("FINDBACK_NOTIFY_MIN_SCORE", raising=False)
    assert notify_min_score() == 0.6
