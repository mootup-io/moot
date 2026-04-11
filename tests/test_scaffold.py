"""Tests for moot init scaffolding."""
from __future__ import annotations

import stat
from pathlib import Path


def test_init_creates_toml(tmp_path: Path, monkeypatch: object) -> None:
    """cmd_init generates valid moot.toml."""
    monkeypatch.chdir(tmp_path)

    class FakeArgs:
        api_url = "https://test.example.com"
        roles = None

    from moot.scaffold import cmd_init

    cmd_init(FakeArgs())

    toml_path = tmp_path / "moot.toml"
    assert toml_path.exists()

    # Verify it's valid TOML
    import tomllib
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    assert data["convo"]["api_url"] == "https://test.example.com"
    assert "product" in data["agents"]
    assert "harness" in data

    # Verify .gitignore was updated
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text()
    assert ".agents.json" in content
    assert ".worktrees/" in content


def test_init_creates_devcontainer(tmp_path: Path, monkeypatch: object) -> None:
    """cmd_init creates .devcontainer/ with all 4 template files."""
    monkeypatch.chdir(tmp_path)

    class FakeArgs:
        api_url = None
        roles = None

    from moot.scaffold import cmd_init

    cmd_init(FakeArgs())

    devcontainer_dir = tmp_path / ".devcontainer"
    assert devcontainer_dir.exists()

    expected_files = {
        "devcontainer.json",
        "post-create.sh",
        "run-moot-mcp.sh",
        "run-moot-channel.sh",
        "run-moot-notify.sh",
    }
    actual_files = {f.name for f in devcontainer_dir.iterdir()}
    assert actual_files == expected_files


def test_init_devcontainer_idempotent(tmp_path: Path, monkeypatch: object) -> None:
    """Running cmd_init twice doesn't overwrite existing .devcontainer/."""
    monkeypatch.chdir(tmp_path)

    class FakeArgs:
        api_url = None
        roles = None

    from moot.scaffold import cmd_init

    cmd_init(FakeArgs())

    # Write a custom file into .devcontainer/
    custom_file = tmp_path / ".devcontainer" / "custom.txt"
    custom_file.write_text("user customization")

    cmd_init(FakeArgs())

    # Custom file should still be present
    assert custom_file.exists()
    assert custom_file.read_text() == "user customization"


def test_template_scripts_executable(tmp_path: Path, monkeypatch: object) -> None:
    """After cmd_init, all .sh files in .devcontainer/ have executable permission."""
    monkeypatch.chdir(tmp_path)

    class FakeArgs:
        api_url = None
        roles = None

    from moot.scaffold import cmd_init

    cmd_init(FakeArgs())

    devcontainer_dir = tmp_path / ".devcontainer"
    for sh_file in devcontainer_dir.glob("*.sh"):
        mode = sh_file.stat().st_mode
        assert mode & stat.S_IEXEC, f"{sh_file.name} is not executable"


def test_init_creates_all_files_together(tmp_path: Path, monkeypatch: object) -> None:
    """A single cmd_init() creates moot.toml, .gitignore, and .devcontainer/."""
    monkeypatch.chdir(tmp_path)

    class FakeArgs:
        api_url = None
        roles = None

    from moot.scaffold import cmd_init

    cmd_init(FakeArgs())

    assert (tmp_path / "moot.toml").exists(), "moot.toml not created"
    assert (tmp_path / ".gitignore").exists(), ".gitignore not created"
    assert (tmp_path / ".devcontainer").is_dir(), ".devcontainer/ not created"
    assert (tmp_path / ".devcontainer" / "devcontainer.json").exists()


def test_launch_includes_channel_flag() -> None:
    """cmd_exec() claude command includes --dangerously-load-development-channels."""
    import inspect
    from moot.launch import cmd_exec

    source = inspect.getsource(cmd_exec)
    assert "--dangerously-load-development-channels" in source, (
        "cmd_exec must include channel flag for push notifications"
    )
    assert "server:convo-channel" in source, (
        "cmd_exec must specify convo-channel server"
    )


def test_init_idempotent(tmp_path: Path, monkeypatch: object) -> None:
    """Running cmd_init twice doesn't duplicate content."""
    monkeypatch.chdir(tmp_path)

    class FakeArgs:
        api_url = None
        roles = None

    from moot.scaffold import cmd_init

    cmd_init(FakeArgs())
    toml_content_1 = (tmp_path / "moot.toml").read_text()
    gitignore_content_1 = (tmp_path / ".gitignore").read_text()

    cmd_init(FakeArgs())
    toml_content_2 = (tmp_path / "moot.toml").read_text()
    gitignore_content_2 = (tmp_path / ".gitignore").read_text()

    # moot.toml should be identical (not overwritten)
    assert toml_content_1 == toml_content_2

    # .gitignore should not have duplicate entries
    assert gitignore_content_1 == gitignore_content_2
