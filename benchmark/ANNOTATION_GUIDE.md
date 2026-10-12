# Annotation Guide — FindBack Real Benchmark

## What counts as "real"?

A real report is one written from an actual lost/found event
(reported by a person, with consent, anonymised), not paraphrased
by the developers to test the matcher. Synthetic rows from
`dataset/findback_reports.csv` must never be copied here.

## Labels (`labels.csv`)

One row per lost report:

| lost_id | expected_found_id | has_match |
|---|---|---|
| L001 | F017 | 1 |
| L002 | (empty) | 0 |

* `has_match = 1`: a single verified found report is the correct match.
  If several found reports could plausibly match, pick the one the
  owner actually reclaimed; note the ambiguity in the review log.
* `has_match = 0`: no valid match exists in `found.csv`. Required
  categories: item lost at a different venue, or item never handed in.
  These cases test the "No Strong Match" threshold.

## Required coverage

Aim for a mix before running the final eval:

1. **Straightforward matches** — same item, same venue, close time.
2. **Ambiguous cases** — vague descriptions ("black phone", "blue bag").
3. **Same-category distractors** — at least 2 found reports sharing the
   lost item's category but belonging to different owners/events.
4. **No-valid-match cases** — at least 10% of lost reports with
   `has_match = 0`.

## Leakage rule

A lost/found pair in `heldout_test/` must not duplicate or
near-duplicate any pair in `dev/` (same wording + same venue/time).
Run `python src/check_leakage.py --dev-dir benchmark/dev --test-dir benchmark/heldout_test`
and resolve every flagged pair (rewording is not enough — replace the event).

## Privacy

Remove names, phone numbers, addresses, and ID numbers from
descriptions before committing. Keep venue names coarse
(e.g. "Central Library, 2nd Floor") unless consent covers detail.
