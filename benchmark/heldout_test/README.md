# HELD-OUT TEST SET — DO NOT TUNE

Do not use this directory for model selection, weight tuning, or
threshold selection.

* Tune only on `benchmark/dev/`.
* Check leakage with `src/check_leakage.py` before final eval.
* Run the final eval exactly once:
  `python src/benchmark_evaluate.py --lost benchmark/heldout_test/lost.csv --found benchmark/heldout_test/found.csv --labels benchmark/heldout_test/labels.csv`
