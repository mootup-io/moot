"""Tests for credential storage."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import stat
from pathlib import Path

import pytest
import respx


def test_login_stores_credential(tmp_path: Path, monkeypatch: object) -> None:
    """store_credential() writes ~/.moot/credentials with mode 600."""
    import moot.auth as auth_mod

    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)  # type: ignore[arg-type]
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)  # type: ignore[arg-type]

    auth_mod.store_credential(
        token="sk-test-123",
        api_url="https://example.com",
        user_id="usr_abc",
    )

    assert cred_file.exists()
    mode = stat.S_IMODE(os.stat(cred_file).st_mode)
    assert mode == 0o600, f"Expected mode 600, got {oct(mode)}"

    content = cred_file.read_text()
    assert "sk-test-123" in content
    assert "https://example.com" in content
    assert "usr_abc" in content


def test_login_reads_credential(tmp_path: Path, monkeypatch: object) -> None:
    """load_credential() round-trips stored data."""
    import moot.auth as auth_mod

    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)  # type: ignore[arg-type]
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)  # type: ignore[arg-type]

    # Store then load
    auth_mod.store_credential(
        token="sk-round-trip",
        api_url="https://rt.example.com",
        user_id="usr_rt",
    )

    cred = auth_mod.load_credential()
    assert cred is not None
    assert cred["token"] == "sk-round-trip"
    assert cred["api_url"] == "https://rt.example.com"
    assert cred["user_id"] == "usr_rt"


def test_login_rejects_non_pat_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """moot login --token convo_key_xxx exits 1 with a friendly error."""
    from moot.auth import cmd_login

    args = argparse.Namespace(token="convo_key_fake_12345", api_url=None)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(cmd_login(args))
    assert exc_info.value.code == 1


def test_login_rejects_empty_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """moot login with empty interactive input exits 1 (falls through to prefix check)."""
    from moot.auth import cmd_login

    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "")

    args = argparse.Namespace(token=None, api_url=None)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(cmd_login(args))
    assert exc_info.value.code == 1


def test_login_interactive_prompt_accepts_valid_pat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """moot login (no --token) prompts via getpass, validates prefix, calls API."""
    import moot.auth as auth_mod
    from moot.auth import cmd_login

    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)

    fake_token = "mootup_pat_" + "a" * 32
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": fake_token)

    args = argparse.Namespace(token=None, api_url="https://mootup.io")

    with respx.mock(base_url="https://mootup.io") as mock:
        mock.get("/api/actors/me").respond(
            200,
            json={"actor_id": "usr_test", "display_name": "Test User"},
        )
        asyncio.run(cmd_login(args))

    assert cred_file.exists()
    content = cred_file.read_text()
    assert fake_token in content


def test_login_token_flag_bypasses_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """moot login --token mootup_pat_... skips the interactive prompt."""
    import moot.auth as auth_mod
    from moot.auth import cmd_login

    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)

    def boom(prompt: str = "") -> str:
        raise AssertionError("getpass.getpass should not be called in --token mode")
    monkeypatch.setattr(getpass, "getpass", boom)

    fake_token = "mootup_pat_" + "b" * 32
    args = argparse.Namespace(token=fake_token, api_url="https://mootup.io")

    with respx.mock(base_url="https://mootup.io") as mock:
        mock.get("/api/actors/me").respond(
            200,
            json={"actor_id": "usr_bypass", "display_name": "Bypass User"},
        )
        asyncio.run(cmd_login(args))

    assert cred_file.exists()
