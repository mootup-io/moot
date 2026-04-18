"""moot.toml and .moot/actors.json loaders."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

MOOT_TOML = "moot.toml"
MOOT_DIR = ".moot"
ACTORS_JSON = f"{MOOT_DIR}/actors.json"

_HARNESS_ALLOWLIST = {"claude-code", "cursor", "aider"}
_MODEL_ALLOWLIST_RE = re.compile(
    r"^(opus|sonnet|haiku|best|default|opusplan|sonnet\[1m\]|opus\[1m\]|claude-[a-z0-9-]+)$"
)
_EFFORT_ALLOWLIST = {"low", "medium", "high", "xhigh", "max"}


def _config_error(msg: str) -> None:
    print(f"Error: {msg}")
    raise SystemExit(1)


class AgentConfig:
    def __init__(
        self,
        role: str,
        data: dict[str, Any],
        *,
        default_harness: str = "claude-code",
        default_model: str | None = None,
        default_effort: str | None = None,
    ) -> None:
        self.role = role
        self.display_name: str = data.get("display_name", role.title())
        self.profile: str = data.get("profile", "devcontainer")
        self.startup_prompt: str = data.get(
            "startup_prompt",
            (
                f"You are the {role.title()} agent. Call orientation() to "
                f"get your identity, focus space, and recent context in one "
                f"call. Then subscribe to the channel and post a "
                f"status_update confirming you are online."
            ),
        )
        self.harness: str = data.get("harness", default_harness)
        self.model: str | None = data.get("model", default_model)
        self.effort: str | None = data.get("effort", default_effort)
        self.theme: str | None = data.get("theme")
        self._raw: dict[str, Any] = data
        self._validate()

    def _validate(self) -> None:
        if self.harness not in _HARNESS_ALLOWLIST:
            _config_error(
                f"agents.{self.role}.harness = {self.harness!r} is not one of "
                f"{sorted(_HARNESS_ALLOWLIST)}"
            )
        if self.model is not None and not _MODEL_ALLOWLIST_RE.match(self.model):
            _config_error(
                f"agents.{self.role}.model = {self.model!r} is not a recognized "
                f"Claude model alias or full ID. Valid aliases: opus, sonnet, "
                f"haiku, best, default, opusplan, sonnet[1m], opus[1m]. Full "
                f"IDs must match claude-<identifier>."
            )
        if self.effort is not None and self.effort not in _EFFORT_ALLOWLIST:
            _config_error(
                f"agents.{self.role}.effort = {self.effort!r} is not one of "
                f"{sorted(_EFFORT_ALLOWLIST)}"
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
        self.default_model: str | None = harness.get("model")
        self.default_effort: str | None = harness.get("effort")
        self.agents: dict[str, AgentConfig] = {}
        for role, agent_data in data.get("agents", {}).items():
            self.agents[role] = AgentConfig(
                role,
                agent_data,
                default_harness=self.harness_type,
                default_model=self.default_model,
                default_effort=self.default_effort,
            )
        # Role the operator talks to directly. `moot up` launches this one
        # first on a cold start (no claude credentials yet) so first-time login
        # happens through its tmux session — the rest of the team starts
        # once credentials exist.
        self.human_interface: str = harness.get(
            "human_interface",
            "product" if "product" in self.agents else (next(iter(self.agents), "")),
        )

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


# ---- Top-level [convo] keys writable by `moot config set` -----------------
#
# Restricted to scalar string keys under [convo] (api_url, space_id,
# template). Agent stanzas and harness settings are not exposed yet —
# editing those requires preserving multi-line stanzas, which a regex
# approach can't safely do. If a user needs to change those, they edit
# moot.toml directly. Adding more keys later means extending this set
# and the regex below.
_SETTABLE_CONVO_KEYS = {"api_url", "space_id", "template"}


def _set_convo_key(key: str, value: str) -> None:
    """Set a top-level [convo] key in moot.toml.

    Walks the file as text rather than round-tripping through a TOML
    serializer, so agent stanzas, comments, and ordering are preserved
    exactly. Replaces the key in place if present (commented or not),
    otherwise appends it inside the [convo] section.
    """
    if key not in _SETTABLE_CONVO_KEYS:
        print(
            f"Error: cannot set '{key}'. "
            f"Settable keys: {', '.join(sorted(_SETTABLE_CONVO_KEYS))}"
        )
        raise SystemExit(1)

    toml_path = Path(MOOT_TOML)
    if not toml_path.exists():
        print(f"Error: {MOOT_TOML} not found in current directory.")
        raise SystemExit(1)

    text = toml_path.read_text()

    # Match an existing line (commented or not) for this key. Catches:
    #   key = "..."
    #   # key = ""  # any trailing comment
    pattern = re.compile(rf"^[ \t]*#?\s*{re.escape(key)}\s*=.*$", re.MULTILINE)
    replacement = f'{key} = "{value}"'
    if pattern.search(text):
        new_text = pattern.sub(replacement, text, count=1)
    else:
        # Inject under [convo] header. Match the first non-empty/non-comment
        # line after [convo] and insert before it. Fail loudly if [convo]
        # header is missing — moot.toml without it is malformed.
        convo_header = re.search(r"^\[convo\]\s*$", text, re.MULTILINE)
        if not convo_header:
            print(f"Error: {MOOT_TOML} has no [convo] section to update.")
            raise SystemExit(1)
        insert_pos = convo_header.end() + 1  # past the trailing newline
        new_text = text[:insert_pos] + replacement + "\n" + text[insert_pos:]

    toml_path.write_text(new_text)
    print(f'Set [convo].{key} = "{value}" in {MOOT_TOML}')


def _render_with_default(value: str | None, default: str | None, tag: str) -> str:
    """Render a field for `moot config show` output.

    If `value` is not None (i.e., the role set the field explicitly in TOML),
    return it. If the role omits it but a default (global or role-derived)
    exists, return "<default> <tag>". If neither is set, return "(unset)".
    """
    if value is not None:
        return value
    if default is not None:
        return f"{default} {tag}"
    return "(unset)"


def cmd_config(args: object) -> None:
    """Handle `moot config show/set/focus`."""
    sub = getattr(args, "config_command", None)
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)
    from moot.scaffold import _ADOPTED_ROLE_DEFAULTS

    if sub == "show" or sub is None:
        print(f"API URL: {config.api_url}")
        print(f"Space ID: {config.space_id or '(not set)'}")
        print(f"Harness: {config.harness_type}")
        gm = config.default_model
        ge = config.default_effort
        if gm is not None or ge is not None:
            gm_s = gm if gm is not None else "(unset)"
            ge_s = ge if ge is not None else "(unset)"
            print(f"Global defaults: model={gm_s}  effort={ge_s}")
        print("Roles:")
        for role_name, agent in config.agents.items():
            raw_model = agent._raw.get("model")
            raw_effort = agent._raw.get("effort")
            model = _render_with_default(raw_model, gm, "(default)")
            effort = _render_with_default(raw_effort, ge, "(default)")
            theme_default = _ADOPTED_ROLE_DEFAULTS.get(role_name.lower(), {}).get(
                "theme"
            )
            theme = _render_with_default(agent.theme, theme_default, "(role default)")
            print(
                f"  {role_name:<16} harness={agent.harness}  "
                f"model={model}  effort={effort}  theme={theme}"
            )
    elif sub == "set":
        key = getattr(args, "key")
        value = getattr(args, "value")
        _set_convo_key(key, value)
    elif sub == "focus":
        space_id = getattr(args, "space_id")
        print(f"TODO: set focus space to {space_id}")
