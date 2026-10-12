"""Leakage-detection tests for src/check_leakage.py (synthetic fixtures)."""

import tests.conftest  # noqa: F401  (path setup)
import check_leakage


def _write_reports(directory, rows):
    directory.mkdir(parents=True, exist_ok=True)
    header = ("report_id,report_type,item_category,description,"
              "organization_type,organization_name\n")
    with open(directory / "lost.csv", "w", encoding="utf-8") as fh:
        fh.write(header)
        for row in rows.get("lost", []):
            fh.write(row + "\n")
    with open(directory / "found.csv", "w", encoding="utf-8") as fh:
        fh.write(header)
        for row in rows.get("found", []):
            fh.write(row + "\n")


def _run(monkeypatch, dev, test, extra=()):
    argv = ["check_leakage", "--dev-dir", str(dev), "--test-dir", str(test),
            *extra]
    monkeypatch.setattr("sys.argv", argv)
    return check_leakage.main()


def test_placeholders_only_is_clean(monkeypatch, tmp_path):
    dev, test = tmp_path / "dev", tmp_path / "test"
    row = ("EXAMPLE-LOST-001,Lost,Backpack,EXAMPLE placeholder,University,"
           "Example University")
    _write_reports(dev, {"lost": [row]})
    _write_reports(test, {"lost": [row]})
    assert _run(monkeypatch, dev, test) == 0


def test_disjoint_reports_are_clean(monkeypatch, tmp_path):
    dev, test = tmp_path / "dev", tmp_path / "test"
    _write_reports(dev, {"lost": ["L001,Lost,Phone,black smartphone lost,Mall,Mall A"]})
    _write_reports(test, {"lost": ["L101,Lost,Wallet,brown leather wallet,Mall,Mall B"]})
    assert _run(monkeypatch, dev, test) == 0


def test_duplicate_id_is_flagged(monkeypatch, tmp_path):
    dev, test = tmp_path / "dev", tmp_path / "test"
    row = "R001,Lost,Phone,black smartphone lost,Mall,Mall A"
    _write_reports(dev, {"lost": [row]})
    _write_reports(test, {"lost": [row]})
    assert _run(monkeypatch, dev, test) == 1


def test_identical_description_is_flagged(monkeypatch, tmp_path):
    dev, test = tmp_path / "dev", tmp_path / "test"
    _write_reports(dev, {"lost": ["D001,Lost,Phone,black smartphone lost near cinema,Mall,Mall A"]})
    _write_reports(test, {"lost": ["T001,Lost,Phone,black smartphone lost near cinema,Mall,Mall B"]})
    assert _run(monkeypatch, dev, test) == 1
