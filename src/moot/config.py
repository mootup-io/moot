"""moot.toml and .moot/actors.json loaders."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

MOOT_TOML = "moot.toml"
MOOT_DIR = ".moot"
ACTORS_JSON = f"{MOOT_DIR}/actors.json"


class AgentConfig:
    def __init__(self, role: str, data: dict[str, Any]) -> None:
        self.role = role
        self.display_name: str = data.get("display_name", role.title())
        self.profile: str = data.get("profile", "devcontainer")
        self.startup_prompt: str = data.get(
            "startup_prompt",
            f"Run your startup protocol from CLAUDE.md. You are the {role.title()} agent.",
        )


class MootConfig:
    def __init__(self, path: Path) -> None:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        convo = data.get("convo", {})
        self.api_url: str = convo.get("api_url", "https://mootup.io")
        self.space_id: str | None = convo.get("space_id")
        harness = data.get("harness", {})
        self.harness_type: str = harness.get("type", "claude-code")
        self.permissions: str = harness.get("permissions", "dangerously-skip")
        self.agents: dict[str, AgentConfig] = {}
        for role, agent_data in data.get("agents", {}).items():
            self.agents[role] = AgentConfig(role, agent_data)

    @property
    def roles(self) -> list[str]:
        return list(self.agents.keys())


def find_config() -> MootConfig | None:
    """Find and parse moot.toml in cwd or parents."""
    path = Path.cwd()
    while path != path.parent:
        toml_path = path / MOOT_TOML
        if toml_path.exists():
            return MootConfig(toml_path)
        path = path.parent
    return None


def load_actors() -> dict[str, Any] | None:
    """Load .moot/actors.json; returns None if missing."""
    path = Path(ACTORS_JSON)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def get_actor_key(role: str) -> str:
    """Return the API key for a role from .moot/actors.json, or ''."""
    data = load_actors()
    if not data:
        return ""
    actors = data.get("actors", {})
    entry = actors.get(role) or actors.get(role.lower()) or {}
    return entry.get("api_key", "")


def load_agent_keys() -> dict[str, str]:
    """Legacy shim: return {role: key} from .moot/actors.json OR .agents.json.

    Kept for the legacy provision path; the new adoption flow uses
    load_actors() / get_actor_key() directly.
    """
    new = load_actors()
    if new:
        return {k: v.get("api_key", "") for k, v in new.get("actors", {}).items()}
    legacy = Path(".agents.json")
    if legacy.exists():
        return json.loads(legacy.read_text())
    return {}


def cmd_config(args: object) -> None:
    """Handle `moot config show/set/focus`."""
    sub = getattr(args, "config_command", None)
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)
    if sub == "show" or sub is None:
        print(f"API URL: {config.api_url}")
        print(f"Space ID: {config.space_id or '(not set)'}")
        print(f"Harness: {config.harness_type}")
        print(f"Roles: {', '.join(config.roles)}")
    elif sub == "set":
        key = getattr(args, "key")
        value = getattr(args, "value")
        print(f"TODO: set {key} = {value}")
    elif sub == "focus":
        space_id = getattr(args, "space_id")
        print(f"TODO: set focus space to {space_id}")
