"""Tests for package structure and zero-backend-imports verification."""
from __future__ import annotations

import subprocess
from pathlib import Path

MOOT_SRC = Path(__file__).resolve().parent.parent / "src"


def test_zero_backend_imports() -> None:
    """No files in src/ import from backend/shared/bridge/api."""
    violations: list[str] = []
    for py_file in MOOT_SRC.rglob("*.py"):
        content = py_file.read_text()
        rel = py_file.relative_to(MOOT_SRC)
        for pattern in ["from shared.", "from backend.", "from bridge.", "from api."]:
            if pattern in content:
                violations.append(f"{rel}: contains '{pattern}'")
    assert not violations, f"Backend import violations:\n" + "\n".join(violations)


def test_package_builds() -> None:
    """uv build succeeds (wheel + sdist)."""
    moot_cli_dir = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["uv", "build"],
        cwd=str(moot_cli_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"uv build failed:\n{result.stderr}"
    # Verify dist/ was created with artifacts
    dist_dir = moot_cli_dir / "dist"
    assert dist_dir.exists(), "dist/ directory not created"
    whl_files = list(dist_dir.glob("*.whl"))
    tar_files = list(dist_dir.glob("*.tar.gz"))
    assert len(whl_files) >= 1, "No wheel file produced"
    assert len(tar_files) >= 1, "No sdist file produced"
