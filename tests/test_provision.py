"""Tests for provision module."""
from __future__ import annotations

import pytest


def test_provision_requires_login(tmp_path, monkeypatch) -> None:
    """cmd_provision exits with error if no credential."""
    import moot.auth as auth_mod

    # Point credential file to a nonexistent path
    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)

    from moot.provision import cmd_provision

    class FakeArgs:
        pass

    with pytest.raises(SystemExit):
        import asyncio
        asyncio.run(cmd_provision(FakeArgs()))
