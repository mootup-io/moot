"""Tests for provision module."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import respx
from httpx import Response


def test_provision_requires_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cmd_provision exits with error if no credential."""
    import moot.auth as auth_mod

    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)

    from moot.provision import cmd_provision

    class FakeArgs:
        pass

    with pytest.raises(SystemExit):
        asyncio.run(cmd_provision(FakeArgs()))


@respx.mock
def test_provision_fresh_writes_moot_agents_fresh_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cmd_provision --fresh writes .moot/agents-fresh.json (not .agents.json)."""
    import moot.auth as auth_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(auth_mod, "CRED_DIR", tmp_path / ".cred")
    monkeypatch.setattr(auth_mod, "CRED_FILE", tmp_path / ".cred" / "credentials")
    auth_mod.store_credential(
        token="mootup_pat_test",
        api_url="https://mootup.io",
        user_id="agt_user",
    )
    (tmp_path / "moot.toml").write_text(
        '[convo]\napi_url = "https://mootup.io"\n'
        '[agents.product]\ndisplay_name = "Product"\n'
        '[harness]\ntype = "claude-code"\n'
    )

    respx.mock.get("https://mootup.io/api/actors/me").mock(
        return_value=Response(
            200,
            json={
                "actor_id": "agt_u",
                "display_name": "Test User",
                "actor_type": "human",
                "sponsor_id": None,
                "tenant_id": "ten_1",
                "is_admin": False,
                "email": None,
                "agent_profile": None,
                "api_key_prefix": None,
                "default_space_id": None,
                "is_connected": None,
                "focus_space_id": None,
                "metadata": None,
                "last_seen_at": None,
                "created_at": "2026-04-18T00:00:00+00:00",
                "updated_at": "2026-04-18T00:00:00+00:00",
            },
        )
    )
    # NOTE: POST /api/tenants/{tenant_id}/agents is a phantom endpoint — not
    # implemented on the convo backend at b6f6d13 (no matching route; not in
    # openapi.yaml). cmd_provision would 404 in production. See
    # docs/specs/oas-mock-refresh.md § 11.F2 — disposition deferred to Product.
    respx.mock.post("https://mootup.io/api/tenants/ten_1/agents").mock(
        return_value=Response(
            201, json={"actor_id": "agt_p", "api_key": "convo_key_fresh"}
        )
    )

    from moot.provision import cmd_provision

    class Args:
        fresh = True

    asyncio.run(cmd_provision(Args()))

    fresh_file = tmp_path / ".moot" / "agents-fresh.json"
    assert fresh_file.exists()
    data = json.loads(fresh_file.read_text())
    assert data["product"] == "convo_key_fresh"
    assert not (tmp_path / ".agents.json").exists()
