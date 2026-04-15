from __future__ import annotations

import os
from pathlib import Path

import httpx

CRED_DIR = Path.home() / ".moot"
CRED_FILE = CRED_DIR / "credentials"

PAT_PREFIX = "mootup_pat_"
DEFAULT_API_URL = "https://mootup.io"


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
    """Handle `moot login [--token <pat>]`."""
    token: str | None = getattr(args, "token", None)
    api_url: str = getattr(args, "api_url", None) or DEFAULT_API_URL

    if not token:
        print(
            "Create a personal access token at "
            "https://mootup.io/settings/api-keys"
        )
        import getpass
        token = getpass.getpass("Paste your token: ")

    if not token.startswith(PAT_PREFIX):
        print(
            "That doesn't look like a Moot personal access token.\n"
            "Tokens start with 'mootup_pat_' — did you paste an agent "
            "API key (convo_key_...) by mistake?"
        )
        raise SystemExit(1)

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
