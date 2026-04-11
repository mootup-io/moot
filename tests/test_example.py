"""Tests for the markdraft example project files."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

EXAMPLE_DIR = Path(__file__).parent.parent.parent / "examples" / "markdraft"
TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "moot" / "templates" / "devcontainer"


def test_moot_toml_valid() -> None:
    """moot.toml parses as valid TOML with exactly 3 agent roles."""
    toml_path = EXAMPLE_DIR / "moot.toml"
    assert toml_path.exists(), f"moot.toml not found: {toml_path}"

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    assert data["convo"]["api_url"] == "https://gemoot.com:8443"
    assert data["harness"]["type"] == "claude-code"

    agents = data["agents"]
    assert set(agents.keys()) == {"product", "implementation", "qa"}
    for role, cfg in agents.items():
        assert "display_name" in cfg, f"agent '{role}' missing display_name"
        assert "startup_prompt" in cfg, f"agent '{role}' missing startup_prompt"


def test_devcontainer_json_valid() -> None:
    """devcontainer.json parses as valid JSON with required fields."""
    dc_path = EXAMPLE_DIR / ".devcontainer" / "devcontainer.json"
    assert dc_path.exists(), f"devcontainer.json not found: {dc_path}"

    with open(dc_path) as f:
        data = json.load(f)

    assert data["postCreateCommand"] == "bash .devcontainer/post-create.sh"
    assert "docker-in-docker" in str(data.get("features", {}))
    assert "python" in str(data.get("features", {}))
    assert "remoteUser" in data


def test_post_create_installs_moot() -> None:
    """post-create.sh contains moot installation with local-wheel fallback."""
    script = (EXAMPLE_DIR / ".devcontainer" / "post-create.sh").read_text()
    assert "pip install moot" in script
    assert ".moot-dist/moot-*.whl" in script


def test_no_convo_specific_paths() -> None:
    """No example file contains convo-specific internal paths."""
    forbidden = [
        "/workspaces/convo/backend",
        "/home/node/convo-venv",
        ".actors.json",
    ]
    for path in EXAMPLE_DIR.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_text(errors="replace")
        for pattern in forbidden:
            assert pattern not in content, (
                f"{path.relative_to(EXAMPLE_DIR)} contains forbidden pattern: {pattern}"
            )
        # Check for bare adapters.mcp_runner (without moot. prefix)
        for line in content.splitlines():
            if "adapters.mcp_runner" in line and "moot.adapters.mcp_runner" not in line:
                assert False, (
                    f"{path.relative_to(EXAMPLE_DIR)} uses bare module path: {line.strip()}"
                )


def test_runner_scripts_unchanged() -> None:
    """Runner scripts are byte-identical to the moot template files."""
    for name in ("run-moot-mcp.sh", "run-moot-channel.sh"):
        example = (EXAMPLE_DIR / ".devcontainer" / name).read_text()
        template = (TEMPLATE_DIR / name).read_text()
        assert example == template, (
            f"{name} differs from template"
        )


def test_gitignore_entries() -> None:
    """.gitignore contains required moot entries."""
    content = (EXAMPLE_DIR / ".gitignore").read_text()
    for entry in [".agents.json", ".env.local", ".worktrees/", ".moot-dist/"]:
        assert entry in content, f".gitignore missing entry: {entry}"
