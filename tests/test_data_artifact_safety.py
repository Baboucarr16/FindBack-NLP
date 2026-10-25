"""Generated evaluation and fixture outputs must not overwrite source data."""

import ast
from pathlib import Path

import pytest

import tests.conftest  # noqa: F401
from artifact_paths import OUTPUT_DIR, output_path


ROOT = Path(__file__).resolve().parents[1]


def test_generated_output_paths_are_contained_in_ignored_output_directory():
    for name in (
        "evaluation_results.csv",
        "model_comparison_results.csv",
        "findback_reports_with_hard_cases.csv",
    ):
        target = output_path(name)
        assert target.parent == OUTPUT_DIR
        assert "dataset" not in target.parts


@pytest.mark.parametrize("unsafe_name", [
    "../dataset/findback_reports.csv",
    "dataset/evaluation_results.csv",
    "",
])
def test_artifact_output_helper_rejects_paths(unsafe_name):
    with pytest.raises(ValueError):
        output_path(unsafe_name)


@pytest.mark.parametrize("filename", [
    "evaluate.py",
    "compare_models.py",
    "add_hard_cases.py",
])
def test_legacy_scripts_route_csv_writes_to_output_file(filename):
    source = (ROOT / "src" / filename).read_text(encoding="utf-8")
    tree = ast.parse(source)
    write_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_csv"
    ]

    assert write_calls
    for call in write_calls:
        assert call.args
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "output_file"

    if filename == "add_hard_cases.py":
        assert 'if __name__ == "__main__"' in source
