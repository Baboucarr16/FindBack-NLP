"""Regression tests for deferred NLP and CSV initialization."""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_isolated(script):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "src"), env.get("PYTHONPATH", "")]
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_wsgi_import_defers_model_and_csv_loading():
    _run_isolated(
        """
import sys
import pandas as pd

def fail_read_csv(*args, **kwargs):
    raise AssertionError("CSV read during application import")

pd.read_csv = fail_read_csv
import app
import wsgi
import semantic_matcher

assert wsgi.application is app.app
assert semantic_matcher.model is None
assert "sentence_transformers" not in sys.modules
"""
    )


def test_model_and_dataset_embeddings_are_reused(tmp_path):
    dataset_path = tmp_path / "reports.csv"
    dataset_path.write_text(
        "report_id,report_type,item_category,description,organization_name,date,approx_time\n"
        "FB001,Lost,Wallet,Wallet missing,Greenfield,2026-08-18,16:20\n"
        "FB002,Found,Wallet,Found leather wallet,Greenfield,2026-08-18,16:30\n",
        encoding="utf-8",
    )
    script = f"""
import sys
import types
import numpy as np

class FakeSentenceTransformer:
    constructions = 0
    encode_batches = []

    def __init__(self, name):
        type(self).constructions += 1

    def encode(self, texts, **kwargs):
        type(self).encode_batches.append(list(texts))
        return np.tile(np.array([[1.0, 0.0]]), (len(texts), 1))

fake_package = types.ModuleType("sentence_transformers")
fake_package.SentenceTransformer = FakeSentenceTransformer
sys.modules["sentence_transformers"] = fake_package

import semantic_matcher
semantic_matcher.DATASET_FILE = {str(dataset_path)!r}

assert semantic_matcher.model is None
lost_report = {{
    "description": "Wallet missing",
    "item_category": "Wallet",
    "organization_name": "Greenfield",
    "date": "2026-08-18",
    "approx_time": "16:20",
}}
first = semantic_matcher.find_semantic_matches_for_report(lost_report)
second = semantic_matcher.find_semantic_matches_for_report(lost_report)

assert first.iloc[0]["report_id"] == "FB002"
assert second.iloc[0]["report_id"] == "FB002"
assert FakeSentenceTransformer.constructions == 1
assert FakeSentenceTransformer.encode_batches == [
    ["Wallet missing", "Found leather wallet"],
    ["Wallet missing"],
    ["Wallet missing"],
]
"""
    _run_isolated(script)
