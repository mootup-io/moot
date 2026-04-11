from __future__ import annotations

import os
from pathlib import Path

import httpx

CRED_DIR = Path.home() / ".moot"
CRED_FILE = CRED_DIR / "credentials"


def load_credential(profile: str = "default") -> dict[str, str] | None:
    """Load stored credential for a profile. Returns None if not found."""
    if not CRED_FILE.exists():
        return None
    import tomllib
    with open(CRED_FILE, "rb") as f:
        data = tomllib.load(f)
    return data.get(profile)


def store_credential(
    token: str,
    api_url: str,
    user_id: str,
    profile: str = "default",
) -> None:
    """Store credential under a profile. Creates ~/.moot/ if needed."""
    CRED_DIR.mkdir(parents=True, exist_ok=True)
    # Read existing
    existing: dict = {}
    if CRED_FILE.exists():
        import tomllib
        with open(CRED_FILE, "rb") as f:
            existing = tomllib.load(f)
    existing[profile] = {
        "api_url": api_url,
        "token": token,
        "user_id": user_id,
    }
    # Write back (simple TOML serialization)
    lines: list[str] = []
    for section, values in existing.items():
        lines.append(f"[{section}]")
        for k, v in values.items():
            lines.append(f'{k} = "{v}"')
        lines.append("")
    CRED_FILE.write_text("\n".join(lines))
    os.chmod(CRED_FILE, 0o600)


async def cmd_login(args: object) -> None:
    """Handle `moot login --token <key>`."""
    token = getattr(args, "token")
    api_url = getattr(args, "api_url") or "https://gemoot.com:8443"

    async with httpx.AsyncClient(
        base_url=api_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    ) as client:
        resp = await client.get("/api/actors/me")
        if resp.status_code != 200:
            print(f"Error: authentication failed ({resp.status_code})")
            raise SystemExit(1)
        actor = resp.json()

    user_id = actor["actor_id"]
    name = actor["display_name"]
    store_credential(token=token, api_url=api_url, user_id=user_id)
    print(f"Authenticated as {name} ({user_id}) on {api_url}")
