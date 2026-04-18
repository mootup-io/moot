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
permissions = "bypassPermissions"
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
    assert config.permissions == "bypassPermissions"
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


class TestAgentProfiles:
    def test_per_role_profile_round_trip(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "moot.toml"
        toml_path.write_text(
            "[convo]\n"
            'api_url = "https://x"\n'
            "\n"
            "[agents.spec]\n"
            'display_name = "Spec"\n'
            'harness = "claude-code"\n'
            'model = "opus"\n'
            'effort = "high"\n'
            'theme = "magenta"\n'
        )
        from moot.config import MootConfig

        config = MootConfig(toml_path)
        spec = config.agents["spec"]
        assert spec.harness == "claude-code"
        assert spec.model == "opus"
        assert spec.effort == "high"
        assert spec.theme == "magenta"

    def test_global_defaults_cascade_to_agent(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "moot.toml"
        toml_path.write_text(
            "[convo]\n"
            'api_url = "https://x"\n'
            "\n"
            "[harness]\n"
            'type = "claude-code"\n'
            'model = "sonnet"\n'
            'effort = "medium"\n'
            "\n"
            "[agents.leader]\n"
            'display_name = "Leader"\n'
        )
        from moot.config import MootConfig

        config = MootConfig(toml_path)
        leader = config.agents["leader"]
        assert leader.model == "sonnet"
        assert leader.effort == "medium"

    def test_invalid_model_rejects_at_load(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        toml_path = tmp_path / "moot.toml"
        toml_path.write_text(
            "[convo]\n"
            'api_url = "https://x"\n'
            "\n"
            "[agents.spec]\n"
            'display_name = "Spec"\n'
            'model = "sonet"\n'
        )
        from moot.config import MootConfig

        with pytest.raises(SystemExit) as excinfo:
            MootConfig(toml_path)
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "spec" in captured.out
        assert "not a recognized Claude model alias" in captured.out

    def test_migration_v1_toml_still_loads(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "moot.toml"
        toml_path.write_text(SAMPLE_TOML)  # pre-run schema
        from moot.config import MootConfig

        config = MootConfig(toml_path)
        for role in config.agents.values():
            assert role.model is None
            assert role.effort is None
            assert role.theme is None


class TestModelAllowlistRegex:
    """Regression guard for _MODEL_ALLOWLIST_RE: known-good aliases must
    match; known-bad strings (typos, whitespace, empty) must not.

    Protects against accidental regex tightening (e.g., dropping the
    claude-* passthrough) or loosening (e.g., letting whitespace slip
    through to the CLI flag).
    """

    def test_known_good_aliases_match(self) -> None:
        from moot.config import _MODEL_ALLOWLIST_RE

        good = [
            "opus",
            "sonnet",
            "haiku",
            "best",
            "default",
            "opusplan",
            "sonnet[1m]",
            "opus[1m]",
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "claude-opus-4-6",
        ]
        for alias in good:
            assert _MODEL_ALLOWLIST_RE.match(alias), f"expected match for {alias!r}"

    def test_known_bad_strings_rejected(self) -> None:
        from moot.config import _MODEL_ALLOWLIST_RE

        bad = [
            "opsu",  # typo
            "sonet",  # typo
            "",  # empty
            "claude-",  # incomplete full ID
            "opus ",  # trailing space
            " opus",  # leading space
        ]
        for alias in bad:
            assert not _MODEL_ALLOWLIST_RE.match(
                alias
            ), f"expected NO match for {alias!r}"


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


class TestCmdConfigShow:
    """Tests for `moot config show` output — Run AF."""

    def _toml(self, body: str) -> str:
        return '[convo]\napi_url = "https://x"\n\n' + body

    def _run_show(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        body: str,
    ) -> str:
        (tmp_path / "moot.toml").write_text(self._toml(body))
        monkeypatch.chdir(tmp_path)
        from argparse import Namespace
        from moot.config import cmd_config

        cmd_config(Namespace(config_command="show"))
        return capsys.readouterr().out

    def test_config_show_prints_all_fields(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = self._run_show(
            tmp_path,
            monkeypatch,
            capsys,
            "[agents.spec]\n"
            'display_name = "Spec"\n'
            'harness = "claude-code"\n'
            'model = "opus"\n'
            'effort = "high"\n'
            'theme = "magenta"\n',
        )
        assert "Roles:" in out
        assert "spec" in out
        assert "harness=claude-code" in out
        assert "model=opus" in out
        assert "effort=high" in out
        assert "theme=magenta" in out

    def test_config_show_cascade_indicator(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = self._run_show(
            tmp_path,
            monkeypatch,
            capsys,
            "[harness]\n"
            'type = "claude-code"\n'
            'model = "sonnet"\n'
            'effort = "medium"\n'
            "\n"
            "[agents.leader]\n"
            'display_name = "Leader"\n',
        )
        assert "Global defaults: model=sonnet  effort=medium" in out
        assert "model=sonnet (default)" in out
        assert "effort=medium (default)" in out

    def test_config_show_role_default_theme(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = self._run_show(
            tmp_path,
            monkeypatch,
            capsys,
            "[agents.product]\n" 'display_name = "Product"\n',
        )
        # Product maps to blue in _ADOPTED_ROLE_DEFAULTS; role-derived default
        # renders with (role default) tag.
        assert "theme=blue (role default)" in out

    def test_config_show_preserves_existing_fields(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = self._run_show(
            tmp_path,
            monkeypatch,
            capsys,
            "[harness]\n"
            'type = "claude-code"\n'
            "\n"
            "[agents.spec]\n"
            'display_name = "Spec"\n',
        )
        assert "API URL: https://x" in out
        assert "Harness: claude-code" in out
        # No Global defaults line when both model + effort unset globally.
        assert "Global defaults:" not in out
        # Unknown/unmapped field renders (unset).
        assert "effort=(unset)" in out

    def test_config_show_unknown_role_theme_unset(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Role not in _ADOPTED_ROLE_DEFAULTS → theme=(unset); guards against
        # AttributeError from the .get({}).get("theme") chain.
        out = self._run_show(
            tmp_path,
            monkeypatch,
            capsys,
            "[agents.custom-role]\n" 'display_name = "Custom"\n',
        )
        assert "theme=(unset)" in out

    def test_config_show_no_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # No moot.toml present → "no moot.toml found" error + SystemExit(1).
        monkeypatch.chdir(tmp_path)
        from argparse import Namespace
        from moot.config import cmd_config
        import pytest as _pytest

        with _pytest.raises(SystemExit) as exc_info:
            cmd_config(Namespace(config_command="show"))
        assert exc_info.value.code == 1
