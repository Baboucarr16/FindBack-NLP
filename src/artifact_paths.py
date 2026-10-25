"""Safe location for generated, non-source project artifacts."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"


def output_path(filename):
    """Return a path under ignored ``outputs/`` for generated results.

    Only a filename is accepted so callers cannot accidentally pass a
    protected dataset path or escape the generated-artifact directory.
    """
    name = Path(filename)
    if (not filename or name.name != str(name)
            or name in {Path("."), Path("..")}):
        raise ValueError("Generated artifact name must be a simple filename.")
    return OUTPUT_DIR / name
