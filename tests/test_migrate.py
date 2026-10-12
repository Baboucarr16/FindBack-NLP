"""Migration planner tests (temporary fixtures; production CSV untouched)."""

import os

import tests.conftest  # noqa: F401  (path setup)
from db.migrate_csv import load_rows, main, to_payload, validate

HEADER = ("report_id,report_type,item_category,description,"
          "organization_type,organization_name,campus_or_branch,"
          "building_or_terminal,floor_or_level,specific_area,"
          "date,approx_time,status\n")

ROW = ("FB001,Lost,Backpack,navy backpack,University,Greenfield University,"
       "Main Campus,Central Library,2nd Floor,Reading Room,"
       "2026-08-18,16:20,Lost\n")


def _write(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(HEADER)
        for row in rows:
            fh.write(row)


def test_dry_run_validates_and_writes_nothing(tmp_path):
    target = tmp_path / "reports.csv"
    _write(target, [ROW])
    before = target.read_bytes()
    assert main(["--csv", str(target)]) == 0
    assert target.read_bytes() == before


def test_validation_catches_duplicates_and_bad_types(tmp_path):
    bad = ROW.replace("FB001", "FB002", 1)
    target = tmp_path / "reports.csv"
    _write(target, [ROW, ROW, bad.replace(",Lost,", ",Missing,")])
    assert main(["--csv", str(target)]) == 1


def test_payload_preserves_legacy_id():
    rows = load_rows(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dataset", "findback_reports.csv"))
    assert len(rows) == 26
    assert validate(rows) == []
    payload = to_payload(rows[0])
    assert payload["legacy_report_id"] == "FB001"
    assert payload["report_type"] == "Lost"
    assert payload["status"] == "active"


def test_execute_without_credentials_fails_cleanly(tmp_path, monkeypatch):
    target = tmp_path / "reports.csv"
    _write(target, [ROW])
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert main(["--csv", str(target), "--execute"]) == 2
