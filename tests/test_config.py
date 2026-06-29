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
            'model = "deepseek v4"\n'  # whitespace — not a single model token
        )
        from moot.config import MootConfig

        with pytest.raises(SystemExit) as excinfo:
            MootConfig(toml_path)
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "spec" in captured.out
        assert "not a valid model identifier" in captured.out

    def test_provider_models_load(self, tmp_path: Path) -> None:
        """Non-Claude / provider-qualified model strings pass validation and
        are forwarded verbatim (routed downstream by the local LLM proxy)."""
        toml_path = tmp_path / "moot.toml"
        toml_path.write_text(
            "[convo]\n"
            'api_url = "https://x"\n'
            "\n"
            "[agents.spec-leader]\n"
            'model = "deepseek-v4-pro"\n'
            "\n"
            "[agents.implementer]\n"
            'model = "accounts/fireworks/models/glm-5p2"\n'
            "\n"
            "[agents.enclave]\n"
            'model = "claude-opus-4-8[1m]"\n'
        )
        from moot.config import MootConfig

        config = MootConfig(toml_path)
        assert config.agents["spec-leader"].model == "deepseek-v4-pro"
        assert (
            config.agents["implementer"].model
            == "accounts/fireworks/models/glm-5p2"
        )
        assert config.agents["enclave"].model == "claude-opus-4-8[1m]"

    def test_per_role_env_parsed(self, tmp_path: Path) -> None:
        """[agents.<role>].env loads as a string table (secret refs are kept
        verbatim; resolution happens at launch, not at config load)."""
        toml_path = tmp_path / "moot.toml"
        toml_path.write_text(
            "[convo]\n"
            'api_url = "https://x"\n'
            "\n"
            "[agents.kernel-implementer]\n"
            'model = "accounts/fireworks/models/glm-5p2"\n'
            'env = { ANTHROPIC_BASE_URL = "http://127.0.0.1:8090", '
            'ANTHROPIC_API_KEY = "${secret:llm-proxy-secret}" }\n'
            "\n"
            "[agents.enclave]\n"
            'model = "claude-opus-4-8[1m]"\n'
        )
        from moot.config import MootConfig

        config = MootConfig(toml_path)
        ki = config.agents["kernel-implementer"]
        assert ki.env == {
            "ANTHROPIC_BASE_URL": "http://127.0.0.1:8090",
            "ANTHROPIC_API_KEY": "${secret:llm-proxy-secret}",
        }
        # Roles with no env default to an empty dict (clean OAuth/subscription).
        assert config.agents["enclave"].env == {}

    def test_env_non_string_value_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        toml_path = tmp_path / "moot.toml"
        toml_path.write_text(
            "[convo]\n"
            'api_url = "https://x"\n'
            "\n"
            "[agents.spec]\n"
            "env = { ANTHROPIC_API_KEY = 123 }\n"  # number, not a string
        )
        from moot.config import MootConfig

        with pytest.raises(SystemExit):
            MootConfig(toml_path)
        assert "env.ANTHROPIC_API_KEY must be a string" in capsys.readouterr().out

    def test_migration_v1_toml_still_loads(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "moot.toml"
        toml_path.write_text(SAMPLE_TOML)  # pre-run schema
        from moot.config import MootConfig

        config = MootConfig(toml_path)
        for role in config.agents.values():
            assert role.model is None
            assert role.effort is None
            assert role.theme is None


class TestPermissionMode:
    def _write(self, tmp_path: Path, harness_block: str) -> Path:
        p = tmp_path / "moot.toml"
        p.write_text(
            '[convo]\napi_url = "https://x"\n'
            + harness_block
            + "\n[agents.spec]\n"
        )
        return p

    def test_default_is_bypass_permissions(self, tmp_path: Path) -> None:
        from moot.config import MootConfig

        config = MootConfig(self._write(tmp_path, ""))
        assert config.permission_mode == "bypassPermissions"

    def test_explicit_mode_honored(self, tmp_path: Path) -> None:
        from moot.config import MootConfig

        config = MootConfig(
            self._write(tmp_path, '[harness]\npermission_mode = "auto"\n')
        )
        assert config.permission_mode == "auto"

    def test_invalid_mode_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from moot.config import MootConfig

        path = self._write(tmp_path, '[harness]\npermission_mode = "yolo"\n')
        with pytest.raises(SystemExit):
            MootConfig(path)
        assert "permission_mode" in capsys.readouterr().out


class TestLaunchStagger:
    def _write(self, tmp_path: Path, harness_block: str) -> Path:
        p = tmp_path / "moot.toml"
        p.write_text(
            '[convo]\napi_url = "https://x"\n' + harness_block + "\n[agents.spec]\n"
        )
        return p

    def test_default_is_two_seconds(self, tmp_path: Path) -> None:
        from moot.config import MootConfig

        assert MootConfig(self._write(tmp_path, "")).launch_stagger_seconds == 2.0

    def test_explicit_value(self, tmp_path: Path) -> None:
        from moot.config import MootConfig

        config = MootConfig(
            self._write(tmp_path, "[harness]\nlaunch_stagger_seconds = 0.5\n")
        )
        assert config.launch_stagger_seconds == 0.5

    def test_negative_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from moot.config import MootConfig

        path = self._write(tmp_path, "[harness]\nlaunch_stagger_seconds = -1\n")
        with pytest.raises(SystemExit):
            MootConfig(path)
        assert "launch_stagger_seconds" in capsys.readouterr().out


class TestModelTokenRegex:
    """Regression guard for _MODEL_TOKEN_RE: well-formed model identifiers
    (Claude aliases, Claude full IDs incl. a "[...]" context suffix, and
    provider-qualified slugs) must match; only empty / whitespace / strings
    with characters that don't belong in a model identifier must not.

    Protects against accidental tightening (e.g., re-dropping provider slugs or
    the "[1m]" suffix) or loosening (e.g., letting whitespace slip through to
    the CLI flag).
    """

    def test_well_formed_models_match(self) -> None:
        from moot.config import _MODEL_TOKEN_RE

        good = [
            # Claude aliases
            "opus",
            "sonnet",
            "haiku",
            "best",
            "default",
            "opusplan",
            "sonnet[1m]",
            "opus[1m]",
            # Claude full IDs, including a context-window suffix
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-opus-4-8[1m]",
            # provider-qualified slugs (routed by the local LLM proxy by prefix)
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "accounts/fireworks/models/glm-5p2",
            "accounts/fireworks/routers/glm-latest[1m]",
        ]
        for model in good:
            assert _MODEL_TOKEN_RE.match(model), f"expected match for {model!r}"

    def test_malformed_strings_rejected(self) -> None:
        from moot.config import _MODEL_TOKEN_RE

        bad = [
            "",  # empty
            "opus ",  # trailing space
            " opus",  # leading space
            "deepseek v4-pro",  # internal whitespace
            "rm -rf /;",  # shell metacharacters
            "model\tname",  # tab
        ]
        for model in bad:
            assert not _MODEL_TOKEN_RE.match(
                model
            ), f"expected NO match for {model!r}"


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
