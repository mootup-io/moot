"""Security-focused tests for moot-cli."""
from __future__ import annotations

import os
import stat
from pathlib import Path


def test_credential_file_not_world_readable(tmp_path: Path, monkeypatch) -> None:
    """Credentials file must be mode 600 (owner read/write only)."""
    import moot.auth as auth_mod

    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)

    auth_mod.store_credential(
        token="secret-token",
        api_url="https://example.com",
        user_id="usr_test",
    )

    mode = stat.S_IMODE(os.stat(cred_file).st_mode)
    # No group or other permissions
    assert mode & stat.S_IRGRP == 0, "Group read not allowed"
    assert mode & stat.S_IWGRP == 0, "Group write not allowed"
    assert mode & stat.S_IROTH == 0, "Other read not allowed"
    assert mode & stat.S_IWOTH == 0, "Other write not allowed"


def test_scaffold_gitignores_secrets(tmp_path: Path, monkeypatch) -> None:
    """moot init adds .agents.json to .gitignore to prevent committing secrets."""
    monkeypatch.chdir(tmp_path)

    class FakeArgs:
        api_url = None
        roles = None

    from moot.scaffold import cmd_init

    cmd_init(FakeArgs())

    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".agents.json" in gitignore, "Agent keys file must be gitignored"
    assert ".env.local" in gitignore, "Local env must be gitignored"


def test_credential_overwrite_preserves_mode(tmp_path: Path, monkeypatch) -> None:
    """Storing a second credential doesn't loosen file permissions."""
    import moot.auth as auth_mod

    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)

    auth_mod.store_credential(token="first", api_url="https://a.com", user_id="u1")
    auth_mod.store_credential(
        token="second", api_url="https://b.com", user_id="u2", profile="staging"
    )

    mode = stat.S_IMODE(os.stat(cred_file).st_mode)
    assert mode == 0o600, f"Expected 600, got {oct(mode)}"

    # Both profiles should be present
    cred_default = auth_mod.load_credential("default")
    cred_staging = auth_mod.load_credential("staging")
    assert cred_default is not None
    assert cred_default["token"] == "first"
    assert cred_staging is not None
    assert cred_staging["token"] == "second"
