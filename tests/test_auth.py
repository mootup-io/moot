"""Tests for credential storage."""
from __future__ import annotations

import os
import stat
from pathlib import Path


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
