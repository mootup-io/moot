"""moot config provision — legacy create-new-agents path."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

from moot.auth import load_credential
from moot.config import MOOT_DIR, find_config


async def cmd_provision(args: object) -> None:
    """Register agents and write the actors file.

    Default: writes .agents.json (legacy).
    --fresh:  writes .moot/agents-fresh.json (per D3).
    """
    cred = load_credential()
    if not cred:
        print("Error: not logged in. Run 'moot login' first.")
        raise SystemExit(1)

    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    fresh = getattr(args, "fresh", False)
    target_path = (
        Path(f"{MOOT_DIR}/agents-fresh.json") if fresh else Path(".agents.json")
    )
    if fresh:
        Path(MOOT_DIR).mkdir(exist_ok=True)

    api_url = config.api_url
    token = cred["token"]

    async with httpx.AsyncClient(
        base_url=api_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    ) as client:
        me_resp = await client.get("/api/actors/me")
        if me_resp.status_code != 200:
            print(f"Error: could not get user info ({me_resp.status_code})")
            raise SystemExit(1)
        me = me_resp.json()
        tenant_id = me.get("tenant_id")
        if not tenant_id:
            print("Error: user has no tenant")
            raise SystemExit(1)

        agent_keys: dict[str, str] = {}
        for role, agent_config in config.agents.items():
            resp = await client.post(
                f"/api/tenants/{tenant_id}/agents",
                json={
                    "display_name": agent_config.display_name,
                    "agent_profile": agent_config.profile,
                },
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                agent_keys[role] = data.get("api_key", "")
                print(f"Provisioned {role}: {data.get('actor_id', '?')}")
            else:
                print(f"Warning: failed to provision {role} ({resp.status_code})")

        target_path.write_text(json.dumps(agent_keys, indent=2))
        print(f"Wrote {target_path} ({len(agent_keys)} agents)")
