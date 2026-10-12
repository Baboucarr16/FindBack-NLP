# FindBack Benchmark

Real, labeled lost-and-found benchmark (in progress — scaffold only).

## Status

No real labeled data has been collected yet. The CSVs under
`dev/` and `heldout_test/` contain headers plus clearly marked
`EXAMPLE` placeholder rows. They are for format validation only
and MUST NOT be presented as performance evidence.

## Layout

```text
benchmark/
  README.md               this file
  schema.json             column contracts for reports + labels
  ANNOTATION_GUIDE.md     how to label real cases
  dev/
    lost.csv              development lost reports (real, once collected)
    found.csv             development found reports (real, once collected)
    labels.csv            dev labels: lost_id -> expected_found_id / has_match
  heldout_test/
    README.md             DO NOT TUNE notice
    lost.csv              held-out lost reports (do not use for tuning)
    found.csv             held-out found reports (do not use for tuning)
    labels.csv            held-out labels (keep sealed until final eval)
```

## Rules

1. Collect real reports first (with consent / anonymised). Do not copy
   rows from `dataset/findback_reports.csv` — that file is synthetic.
2. Tune models and any "No Strong Match" threshold on `dev/` only.
3. Run on `heldout_test/` exactly once for the final report.
4. Run `python src/check_leakage.py` before final eval to confirm no
   duplicate or near-duplicate leakage between dev and test.
5. Evaluate with `python src/benchmark_evaluate.py` — reports
   Top-1 / Top-3 / Top-5, MRR, nDCG, plus abstention stats when
   `--threshold` is supplied.
