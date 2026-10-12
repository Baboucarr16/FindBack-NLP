"""CSV -> Supabase migration planner (read-only by default).

Default mode validates dataset/findback_reports.csv and prints the
migration plan without touching the CSV or any database. Use
--execute only with SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY set;
even then the CSV is only ever read, never overwritten or deleted.

Usage:
    python db/migrate_csv.py
    python db/migrate_csv.py --csv dataset/findback_reports.csv
    python db/migrate_csv.py --execute   # needs credentials
"""

import argparse
import csv
import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".env"))
except ImportError:
    pass

EXPECTED_COLUMNS = [
    "report_id", "report_type", "item_category", "description",
    "organization_type", "organization_name", "campus_or_branch",
    "building_or_terminal", "floor_or_level", "specific_area",
    "date", "approx_time", "status",
]


def load_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(
                "Unexpected columns: %s" % (reader.fieldnames,)
            )
        return list(reader)


def validate(rows):
    errors = []
    seen = set()
    for line, row in enumerate(rows, start=2):
        rid = row.get("report_id", "").strip()
        if not rid:
            errors.append("line %d: missing report_id" % line)
        elif rid in seen:
            errors.append("line %d: duplicate report_id %s" % (line, rid))
        seen.add(rid)
        if row.get("report_type") not in ("Lost", "Found"):
            errors.append("line %d: bad report_type %r" % (line, row.get("report_type")))
        if not row.get("description", "").strip():
            errors.append("line %d: empty description (%s)" % (line, rid))
    return errors


def to_payload(row, owner_id=None):
    return {
        "owner_id": owner_id,
        "report_type": row["report_type"],
        "item_category": row.get("item_category", ""),
        "description": row.get("description", ""),
        "organization_type": row.get("organization_type", ""),
        "organization_name": row.get("organization_name", ""),
        "campus_or_branch": row.get("campus_or_branch", ""),
        "building_or_terminal": row.get("building_or_terminal", ""),
        "floor_or_level": row.get("floor_or_level", ""),
        "specific_area": row.get("specific_area", ""),
        "event_date": row.get("date", "") or None,
        "approx_time": row.get("approx_time", "") or None,
        "status": "active",
        "legacy_report_id": row.get("report_id", ""),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan or run the CSV migration.")
    parser.add_argument("--csv", default="dataset/findback_reports.csv")
    parser.add_argument("--execute", action="store_true",
                        help="Insert rows (requires Supabase credentials).")
    args = parser.parse_args(argv)

    rows = load_rows(args.csv)
    errors = validate(rows)
    lost = sum(1 for r in rows if r["report_type"] == "Lost")
    found = sum(1 for r in rows if r["report_type"] == "Found")
    print("Rows: %d (%d Lost, %d Found)" % (len(rows), lost, found))
    if errors:
        print("Validation errors:")
        for err in errors:
            print("  - %s" % err)
        return 1
    print("Validation: OK, no duplicate IDs, no empty descriptions.")

    if not args.execute:
        print("Dry run: nothing was written. Re-run with --execute "
              "to insert (CSV is only read in both modes).")
        return 0

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("ERROR: --execute needs SUPABASE_URL and "
              "SUPABASE_SERVICE_ROLE_KEY in the environment.")
        return 2
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: the 'supabase' package is not installed. "
              "Run: pip install -r requirements.txt")
        return 2

    client = create_client(url, key)
    payloads = [to_payload(r) for r in rows]
    # legacy_report_id is unique: re-runs skip already-migrated rows.
    existing = {r["legacy_report_id"] for r in
                client.table("reports").select("legacy_report_id").execute().data}
    fresh = [p for p in payloads if p["legacy_report_id"] not in existing]
    print("Already migrated: %d, to insert: %d" % (len(payloads) - len(fresh), len(fresh)))
    for i in range(0, len(fresh), 100):
        client.table("reports").insert(fresh[i:i + 100]).execute()
    print("Migration complete. Original CSV left untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
