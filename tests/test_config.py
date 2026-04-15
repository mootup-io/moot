"""Tests for moot.toml config parsing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


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


def test_actors_json_constant() -> None:
    """ACTORS_JSON constant points at .moot/actors.json."""
    from moot.config import ACTORS_JSON

    assert ACTORS_JSON == ".moot/actors.json"


def test_load_actors_returns_none_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    from moot.config import load_actors

    assert load_actors() is None


def test_load_actors_parses_nested_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".moot").mkdir()
    (tmp_path / ".moot" / "actors.json").write_text(
        json.dumps(
            {
                "space_id": "spc_1",
                "space_name": "Test",
                "api_url": "https://mootup.io",
                "actors": {
                    "product": {
                        "actor_id": "agt_1",
                        "api_key": "convo_key_p",
                        "display_name": "Product",
                    }
                },
            }
        )
    )
    from moot.config import load_actors

    data = load_actors()
    assert data is not None
    assert data["space_id"] == "spc_1"
    assert data["actors"]["product"]["api_key"] == "convo_key_p"


def test_get_actor_key_returns_role_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".moot").mkdir()
    (tmp_path / ".moot" / "actors.json").write_text(
        json.dumps(
            {
                "space_id": "spc_1",
                "space_name": "",
                "api_url": "",
                "actors": {
                    "product": {
                        "actor_id": "a",
                        "api_key": "convo_key_p",
                        "display_name": "Product",
                    },
                    "qa": {
                        "actor_id": "a",
                        "api_key": "convo_key_q",
                        "display_name": "QA",
                    },
                },
            }
        )
    )
    from moot.config import get_actor_key

    assert get_actor_key("product") == "convo_key_p"
    assert get_actor_key("qa") == "convo_key_q"
    assert get_actor_key("missing") == ""
