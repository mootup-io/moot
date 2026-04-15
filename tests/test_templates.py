"""Tests for bundled devcontainer and team template files."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from moot.scaffold import (
    BUNDLED_SKILLS,
    DEVCONTAINER_TEMPLATE_DIR,
    SKILLS_TEMPLATE_DIR,
)
from moot.team_profile import (
    TEAMS_DIR,
    TeamProfile,
    generate_claude_md,
    generate_moot_toml,
    resolve_template,
)


# -- Devcontainer template tests (existing) ----------------------------------


def test_template_dir_exists() -> None:
    """DEVCONTAINER_TEMPLATE_DIR resolves to a directory with the expected files."""
    assert DEVCONTAINER_TEMPLATE_DIR.is_dir(), f"Template dir not found: {DEVCONTAINER_TEMPLATE_DIR}"
    expected = {
        "devcontainer.json",
        "post-create.sh",
        "run-moot-mcp.sh",
        "run-moot-channel.sh",
        "run-moot-notify.sh",
    }
    actual = {f.name for f in DEVCONTAINER_TEMPLATE_DIR.iterdir()}
    assert actual == expected


def test_devcontainer_json_valid() -> None:
    """Bundled devcontainer.json is valid JSON with required fields."""
    content = (DEVCONTAINER_TEMPLATE_DIR / "devcontainer.json").read_text()
    data = json.loads(content)
    assert "name" in data
    assert "image" in data
    assert "postCreateCommand" in data


def test_runner_scripts_no_convo_paths() -> None:
    """Template runner scripts contain no hardcoded convo-specific paths."""
    forbidden = [
        "/workspaces/convo",
        "convo-venv",
        ".agents.json",  # post-Run-R: renamed to .moot/actors.json
        "gemoot.com",
    ]
    for script_name in ("run-moot-mcp.sh", "run-moot-channel.sh", "run-moot-notify.sh"):
        content = (DEVCONTAINER_TEMPLATE_DIR / script_name).read_text()
        for pattern in forbidden:
            assert pattern not in content, (
                f"{script_name} contains forbidden pattern: {pattern}"
            )
        # Verify moot.adapters prefix (not bare adapters.mcp_runner)
        assert "moot.adapters." in content, (
            f"{script_name} should use moot.adapters.* module path"
        )


def test_runner_reads_actors_json() -> None:
    """Runner scripts reference .moot/actors.json (nested shape), not .agents.json."""
    for script_name in ("run-moot-mcp.sh", "run-moot-channel.sh", "run-moot-notify.sh"):
        content = (DEVCONTAINER_TEMPLATE_DIR / script_name).read_text()
        assert ".moot/actors.json" in content, (
            f"{script_name} should reference .moot/actors.json"
        )
        assert ".agents.json" not in content, (
            f"{script_name} should not reference .agents.json"
        )
        assert "data.get('actors'" in content, (
            f"{script_name} should parse the nested actors.json schema"
        )


def test_skills_bundle_complete() -> None:
    """All 7 bundled skills exist and contain no convo-specific strings."""
    for skill in BUNDLED_SKILLS:
        skill_md = SKILLS_TEMPLATE_DIR / skill / "SKILL.md"
        assert skill_md.exists(), f"{skill}/SKILL.md missing from bundle"
        content = skill_md.read_text()
        forbidden = [
            "/workspaces/convo",
            "Pat",
            "feedback_",
            "Arch Run",
            "agt_",
            "evt_",
            "spc_",
            "docker exec convo-",
        ]
        for pattern in forbidden:
            assert pattern not in content, (
                f"{skill}/SKILL.md contains forbidden pattern: {pattern}"
            )


def test_devcontainer_no_convo_customizations() -> None:
    """devcontainer.json has no runArgs, mounts, or convo-specific extensions."""
    content = (DEVCONTAINER_TEMPLATE_DIR / "devcontainer.json").read_text()
    data = json.loads(content)
    assert "runArgs" not in data, "Template should not have runArgs"
    assert "mounts" not in data, "Template should not have mounts"
    extensions = data.get("customizations", {}).get("vscode", {}).get("extensions", [])
    convo_extensions = ["svelte.svelte-vscode", "dbaeumer.vscode-eslint", "esbenp.prettier-vscode"]
    for ext in convo_extensions:
        assert ext not in extensions, f"Template should not include convo-specific extension: {ext}"


def test_post_create_no_convo_paths() -> None:
    """post-create.sh has no hardcoded convo-specific paths or packages."""
    content = (DEVCONTAINER_TEMPLATE_DIR / "post-create.sh").read_text()
    forbidden = [
        "/workspaces/convo",
        "convo-venv",
        "gemoot.com",
        "run-convo-",
        "SSL_CERT_FILE",
    ]
    for pattern in forbidden:
        assert pattern not in content, (
            f"post-create.sh contains forbidden pattern: {pattern}"
        )
    # Must install moot
    assert "pip install moot" in content, "post-create.sh should install moot"


def test_runner_scripts_read_moot_toml() -> None:
    """Runner scripts read config from moot.toml, not .env.local."""
    for script_name in ("run-moot-mcp.sh", "run-moot-channel.sh", "run-moot-notify.sh"):
        content = (DEVCONTAINER_TEMPLATE_DIR / script_name).read_text()
        assert "moot.toml" in content, (
            f"{script_name} should read config from moot.toml"
        )
        assert ".env.local" not in content, (
            f"{script_name} should not reference .env.local"
        )


def test_channel_runner_logs_stderr() -> None:
    """Channel runner script redirects stderr to a log file."""
    content = (DEVCONTAINER_TEMPLATE_DIR / "run-moot-channel.sh").read_text()
    assert "2>" in content, "Channel runner should redirect stderr"
    assert "LOG_FILE" in content, "Channel runner should define LOG_FILE"


# -- TeamProfile parsing tests -----------------------------------------------


class TestTeamProfileParsing:
    def test_parse_loop4_team_toml(self) -> None:
        """Parse loop-4 team.toml. Assert 4 roles, pipeline order, git ownership, threads."""
        path = TEAMS_DIR / "loop-4" / "team.toml"
        profile = TeamProfile.from_toml(path)

        assert profile.name == "loop-4"
        assert len(profile.roles) == 4
        assert [r.name for r in profile.roles] == ["product", "spec", "implementation", "qa"]
        assert profile.workflow.pipeline == ["product", "spec", "implementation", "qa"]
        assert profile.git.ownership["main_branch"] == "product"
        assert profile.workflow.threads["feature"] == "[FEATURE]"
        assert profile.workflow.threads["question"] == "[QUESTION]"

    def test_parse_loop3_team_toml(self) -> None:
        """Parse loop-3 team.toml. Assert 3 roles, correct pipeline."""
        path = TEAMS_DIR / "loop-3" / "team.toml"
        profile = TeamProfile.from_toml(path)

        assert profile.name == "loop-3"
        assert len(profile.roles) == 3
        assert [r.name for r in profile.roles] == ["leader", "implementation", "qa"]
        assert profile.workflow.pipeline == ["leader", "implementation", "qa"]

    def test_parse_loop4_observer_team_toml(self) -> None:
        """Parse loop-4-observer. Assert 5 roles, librarian has cursor harness, pipeline has 4."""
        path = TEAMS_DIR / "loop-4-observer" / "team.toml"
        profile = TeamProfile.from_toml(path)

        assert profile.name == "loop-4-observer"
        assert len(profile.roles) == 5
        librarian = [r for r in profile.roles if r.name == "librarian"][0]
        assert librarian.harness == "cursor"
        # Librarian is NOT in the pipeline
        assert len(profile.workflow.pipeline) == 4
        assert "librarian" not in profile.workflow.pipeline

    def test_role_defaults(self, tmp_path: Path) -> None:
        """Parse a minimal team.toml with only name. Assert defaults."""
        minimal = tmp_path / "team.toml"
        minimal.write_text("""
[team]
name = "minimal"

[[roles]]
name = "agent1"
""")
        profile = TeamProfile.from_toml(minimal)

        assert profile.name == "minimal"
        assert len(profile.roles) == 1
        assert profile.roles[0].name == "agent1"
        assert profile.roles[0].display_name == "Agent1"
        assert profile.roles[0].harness == "claude-code"
        assert profile.roles[0].responsibilities == ""
        assert profile.roles[0].startup_prompt == ""


# -- Template resolver tests --------------------------------------------------


class TestTemplateResolver:
    def test_resolve_builtin_template(self) -> None:
        """resolve_template('loop-4') returns the loop-4 directory."""
        path = resolve_template("loop-4")
        assert path.is_dir()
        assert (path / "team.toml").exists()
        assert path.name == "loop-4"

    def test_resolve_local_path(self, tmp_path: Path) -> None:
        """resolve_template with a local path returns that directory."""
        team_toml = tmp_path / "team.toml"
        team_toml.write_text('[team]\nname = "custom"\n')
        path = resolve_template(str(tmp_path))
        assert path == tmp_path

    def test_resolve_unknown_raises(self) -> None:
        """resolve_template('nonexistent') raises FileNotFoundError with available list."""
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            resolve_template("nonexistent")


# -- moot.toml generation tests -----------------------------------------------


class TestMootTomlGeneration:
    def test_generate_moot_toml_from_loop4(self) -> None:
        """Generate moot.toml from loop-4 profile. Parse output, verify structure."""
        path = TEAMS_DIR / "loop-4" / "team.toml"
        profile = TeamProfile.from_toml(path)
        content = generate_moot_toml(profile, "https://example.com:8443")

        # Parse the generated TOML
        data = tomllib.loads(content)
        assert data["convo"]["api_url"] == "https://example.com:8443"
        assert data["convo"]["template"] == "loop-4"

        # 4 agent sections
        agents = data["agents"]
        assert len(agents) == 4
        assert "product" in agents
        assert "spec" in agents
        assert "implementation" in agents
        assert "qa" in agents

        # Check display names
        assert agents["product"]["display_name"] == "Product"
        assert agents["qa"]["display_name"] == "QA"

        # Harness
        assert data["harness"]["type"] == "claude-code"

    def test_generate_moot_toml_includes_template_metadata(self) -> None:
        """Verify generated moot.toml contains template metadata in [convo] section."""
        path = TEAMS_DIR / "loop-4" / "team.toml"
        profile = TeamProfile.from_toml(path)
        content = generate_moot_toml(profile, "https://example.com")

        data = tomllib.loads(content)
        assert data["convo"]["template"] == "loop-4"


# -- CLAUDE.md generation tests -----------------------------------------------


class TestClaudeMdGeneration:
    def test_generate_claude_md_fills_placeholders(self) -> None:
        """Generate CLAUDE.md from loop-4. Assert placeholders are filled."""
        template_dir = TEAMS_DIR / "loop-4"
        profile = TeamProfile.from_toml(template_dir / "team.toml")
        content = generate_claude_md(profile, template_dir, "Test Project")

        # No unfilled template placeholders remain
        # (git convention patterns like {slug} and {role} are legitimate literals)
        import re
        # Find {word} patterns that aren't doubled-brace
        unfilled = re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", content)
        # Filter out git branch convention patterns
        git_patterns = {"slug", "role"}
        unfilled = [p for p in unfilled if p not in git_patterns]
        assert unfilled == [], f"Unfilled placeholders: {unfilled}"

        # Content checks
        assert "4 agents" in content
        assert "**Product**" in content
        assert "**QA**" in content
        assert "Product --> Spec --> Implementation --> Qa --> Product" in content

    def test_generate_claude_md_preserves_todo(self) -> None:
        """Assert generated CLAUDE.md contains TODO: markers."""
        template_dir = TEAMS_DIR / "loop-4"
        profile = TeamProfile.from_toml(template_dir / "team.toml")
        content = generate_claude_md(profile, template_dir)

        assert "TODO:" in content


# -- QA coverage tests ---------------------------------------------------------


class TestTeamTemplatesQA:
    """QA-authored tests extending coverage beyond impl gate."""

    def test_all_builtin_templates_parseable(self) -> None:
        """Every directory in templates/teams/ has a valid, parseable team.toml."""
        assert TEAMS_DIR.is_dir()
        template_dirs = sorted(d for d in TEAMS_DIR.iterdir() if d.is_dir())
        assert len(template_dirs) == 5, f"Expected 5 templates, found {len(template_dirs)}"
        for d in template_dirs:
            toml_path = d / "team.toml"
            assert toml_path.exists(), f"{d.name} missing team.toml"
            profile = TeamProfile.from_toml(toml_path)
            assert profile.name == d.name, f"{d.name}: name mismatch (got '{profile.name}')"
            assert len(profile.roles) >= 3, f"{d.name}: fewer than 3 roles"
            assert len(profile.workflow.pipeline) >= 3, f"{d.name}: pipeline too short"

    def test_all_builtin_templates_generate_claude_md(self) -> None:
        """Generate CLAUDE.md for every built-in template. No unfilled placeholders."""
        import re
        git_patterns = {"slug", "role"}
        for d in sorted(TEAMS_DIR.iterdir()):
            if not d.is_dir():
                continue
            profile = TeamProfile.from_toml(d / "team.toml")
            content = generate_claude_md(profile, d, "Test Project")
            unfilled = re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", content)
            unfilled = [p for p in unfilled if p not in git_patterns]
            assert unfilled == [], f"{d.name}: unfilled placeholders: {unfilled}"
            assert "TODO:" in content, f"{d.name}: missing TODO markers"

    def test_split_leader_pipeline_excludes_product(self) -> None:
        """loop-4-split-leader pipeline goes through 'lead', not 'product'."""
        profile = TeamProfile.from_toml(TEAMS_DIR / "loop-4-split-leader" / "team.toml")
        assert "lead" in profile.workflow.pipeline
        assert "product" not in profile.workflow.pipeline
        assert profile.git.ownership["main_branch"] == "lead"
        assert profile.resources.owners["git"] == "lead"

    def test_observer_not_in_pipeline(self) -> None:
        """loop-4-observer's librarian exists as a role but is NOT in the pipeline."""
        profile = TeamProfile.from_toml(TEAMS_DIR / "loop-4-observer" / "team.toml")
        role_names = [r.name for r in profile.roles]
        assert "librarian" in role_names
        assert "librarian" not in profile.workflow.pipeline
        librarian = [r for r in profile.roles if r.name == "librarian"][0]
        assert librarian.harness == "cursor"

    def test_resolver_error_lists_available_templates(self) -> None:
        """FileNotFoundError from resolve_template includes all 5 template names."""
        with pytest.raises(FileNotFoundError, match="Available:") as exc_info:
            resolve_template("nonexistent-template")
        msg = str(exc_info.value)
        for name in ("loop-3", "loop-4", "loop-4-observer", "loop-4-parallel", "loop-4-split-leader"):
            assert name in msg, f"Error message missing template '{name}'"

    def test_loop3_verifier_display_name(self) -> None:
        """loop-3 qa role has display_name 'Verifier', not 'QA'."""
        profile = TeamProfile.from_toml(TEAMS_DIR / "loop-3" / "team.toml")
        qa_role = [r for r in profile.roles if r.name == "qa"][0]
        assert qa_role.display_name == "Verifier"

    def test_parallel_has_two_implementers(self) -> None:
        """loop-4-parallel has both implementation_a and implementation_b roles."""
        profile = TeamProfile.from_toml(TEAMS_DIR / "loop-4-parallel" / "team.toml")
        assert len(profile.roles) == 5
        role_names = [r.name for r in profile.roles]
        assert "implementation_a" in role_names
        assert "implementation_b" in role_names
        # Only one is in the pipeline (leader dispatches)
        assert "implementation_a" in profile.workflow.pipeline

    def test_generate_moot_toml_loop3(self) -> None:
        """Generate moot.toml from loop-3. Assert 3 agent sections."""
        profile = TeamProfile.from_toml(TEAMS_DIR / "loop-3" / "team.toml")
        content = generate_moot_toml(profile, "https://example.com")
        data = tomllib.loads(content)
        assert data["convo"]["template"] == "loop-3"
        assert len(data["agents"]) == 3
        assert "leader" in data["agents"]
        assert "implementation" in data["agents"]
        assert "qa" in data["agents"]
