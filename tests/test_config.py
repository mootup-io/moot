"""Tests for moot.toml config parsing."""
from __future__ import annotations

from pathlib import Path


SAMPLE_TOML = """\
[convo]
api_url = "https://example.com:8443"
space_id = "spc_abc123"

[agents.product]
display_name = "Product"
profile = "devcontainer"
startup_prompt = "You are Product."

[agents.spec]
display_name = "Spec"

[harness]
type = "claude-code"
permissions = "dangerously-skip-permissions"
"""


def test_config_parse_full(tmp_path: Path) -> None:
    """MootConfig correctly parses a complete moot.toml with all fields."""
    toml_path = tmp_path / "moot.toml"
    toml_path.write_text(SAMPLE_TOML)

    from moot.config import MootConfig

    config = MootConfig(toml_path)
    assert config.api_url == "https://example.com:8443"
    assert config.space_id == "spc_abc123"
    assert config.harness_type == "claude-code"
    assert config.permissions == "dangerously-skip-permissions"
    assert set(config.roles) == {"product", "spec"}
    assert config.agents["product"].display_name == "Product"
    assert config.agents["product"].profile == "devcontainer"
    assert config.agents["product"].startup_prompt == "You are Product."
    # Spec has defaults for profile and startup_prompt
    assert config.agents["spec"].display_name == "Spec"
    assert config.agents["spec"].profile == "devcontainer"
    assert "Spec" in config.agents["spec"].startup_prompt


def test_config_find_walks_parents(tmp_path: Path, monkeypatch: object) -> None:
    """find_config() searches parent directories."""
    # Write moot.toml at tmp_path root
    toml_path = tmp_path / "moot.toml"
    toml_path.write_text(SAMPLE_TOML)

    # Create a nested directory and cd into it
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    import moot.config as config_mod
    monkeypatch.setattr(Path, "cwd", lambda: nested)  # type: ignore[arg-type]

    config = config_mod.find_config()
    assert config is not None
    assert config.api_url == "https://example.com:8443"
