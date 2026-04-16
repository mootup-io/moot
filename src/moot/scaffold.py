"""moot init — full provisioning flow.

Adopts the user's default-space keyless agents, rotates their keys,
writes .moot/actors.json, installs bundled skills / CLAUDE.md /
devcontainer with conflict-aware staging, and emits .moot/init-report.md.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from moot.auth import load_credential
from moot.config import ACTORS_JSON, MOOT_DIR
from moot.team_profile import (
    RoleProfile,
    TeamProfile,
    generate_moot_toml,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
DEVCONTAINER_TEMPLATE_DIR = TEMPLATES_DIR / "devcontainer"
SKILLS_TEMPLATE_DIR = TEMPLATES_DIR / "skills"
CLAUDE_MD_TEMPLATE = TEMPLATES_DIR / "CLAUDE.md"

GITIGNORE_ENTRIES = [".moot/", ".agents.json", ".env.local", ".worktrees/"]

BUNDLED_SKILLS = (
    "product-workflow",
    "spec-checklist",
    "leader-workflow",
    "librarian-workflow",
    "handoff",
    "verify",
    "doc-curation",
)


def cmd_init(args: object) -> None:
    """Synchronous entry; delegates to async runner."""
    asyncio.run(_cmd_init_async(args))


async def _cmd_init_async(args: object) -> None:
    """Handle `moot init [--force|--update-suggestions|--adopt-fresh-install|--fresh]`."""
    if getattr(args, "fresh", False):
        from moot.provision import cmd_provision
        await cmd_provision(args)
        return

    force = getattr(args, "force", False)
    update_suggestions = getattr(args, "update_suggestions", False)
    adopt_fresh = getattr(args, "adopt_fresh_install", False)
    yes = getattr(args, "yes", False)

    if not Path(".git").exists():
        print(
            "Warning: this doesn't look like a git repository; "
            ".moot/ and .claude/skills/ won't be versioned."
        )

    if update_suggestions:
        await _update_suggestions_only()
        return

    actors_path = Path(ACTORS_JSON)
    if actors_path.exists() and not force and not adopt_fresh:
        print(
            f"Error: {actors_path} already exists.\n"
            f"Use `moot init --force` to rotate keys (invalidates the current set),\n"
            f"or `moot init --update-suggestions` to refresh staged suggestions only."
        )
        raise SystemExit(1)

    cred = load_credential()
    if not cred:
        print("Error: not logged in. Run 'moot login' first.")
        raise SystemExit(1)

    api_url = cred["api_url"]
    token = cred["token"]

    async with httpx.AsyncClient(
        base_url=api_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    ) as client:
        print(f"Using profile default (authenticated on {api_url})")
        actor, space_id, space_name = await _fetch_actor_and_space(client)
        print(f"Fetched your default space: {space_id} ({space_name})")

        keyless = await _fetch_keyless_agents(client, force=force)
        if not keyless and not force:
            print(
                "Error: no keyless agents found in your default space.\n"
                "If you've run `moot init` before on this space, use "
                "`moot init --force` to rotate the existing keys."
            )
            raise SystemExit(1)
        if not keyless and force:
            print("Error: no agents found in your default space to adopt.")
            raise SystemExit(1)

        adopt_label = "agents" if force else "keyless agents"
        print(f"Found {len(keyless)} {adopt_label} in default space:")
        for agent in keyless:
            print(f"  - {agent['display_name']:16s} ({agent['actor_id']})")

        if force and not yes:
            _prompt_or_exit(
                f"This will rotate keys for {len(keyless)} agents. "
                f"Currently-connected agents will disconnect. Continue? [y/N] "
            )
        if adopt_fresh and not yes:
            _prompt_or_exit(
                "This will overwrite CLAUDE.md, .claude/skills/, and "
                ".devcontainer/ with bundled content, potentially losing "
                "your local changes. Continue? [y/N] "
            )

        print("\nRotating keys for keyless agents...")
        adopted = await _rotate_keys(client, keyless, force=force)

    _write_actors_json(
        space_id=space_id,
        space_name=space_name,
        api_url=api_url,
        adopted=adopted,
    )
    print(f"Wrote {ACTORS_JSON}              ({len(adopted)} agents, chmod 600)")

    _write_moot_toml_from_adopted(
        adopted=adopted, api_url=api_url, space_id=space_id, force=force
    )

    _update_gitignore()

    conflicts = _install_bundles(
        adopted=adopted,
        space_id=space_id,
        space_name=space_name,
        api_url=api_url,
        overwrite=adopt_fresh,
    )

    _write_init_report(
        space_id=space_id,
        space_name=space_name,
        api_url=api_url,
        adopted=adopted,
        conflicts=conflicts,
    )

    print("\nDone. See .moot/init-report.md for details and next steps.")


async def _fetch_actor_and_space(
    client: httpx.AsyncClient,
) -> tuple[dict[str, Any], str, str]:
    """GET /api/actors/me → (actor_dict, default_space_id, default_space_name)."""
    resp = await client.get("/api/actors/me")
    if resp.status_code != 200:
        print(
            f"Error: could not fetch your account ({resp.status_code}). "
            f"Your credential may have expired — run `moot login` again."
        )
        raise SystemExit(1)
    actor = resp.json()
    space_id = actor.get("default_space_id")
    if not space_id:
        print("Error: your account has no default space. Contact support.")
        raise SystemExit(1)

    space_resp = await client.get(f"/api/spaces/{space_id}")
    space_name = (
        space_resp.json().get("name", space_id)
        if space_resp.status_code == 200
        else space_id
    )
    return actor, space_id, space_name


async def _fetch_keyless_agents(
    client: httpx.AsyncClient,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    """List the user's sponsored agents to adopt.

    Without `force`: only keyless agents (api_key_prefix is None) — the
    first-time-setup case where default-space provisioning created agents
    that haven't been claimed yet.

    With `force`: ALL sponsored agents, keyless or keyed. This matches the
    cli's own user-facing message ("If you've run `moot init` before on
    this space, use `moot init --force` to rotate the existing keys") —
    a forced re-init re-rotates every key, not just the never-issued ones.

    Background: originally called /api/spaces/{id}/participants, which
    returns Participant objects (`name`, `participant_id`, no
    `api_key_prefix`); switched to /api/actors/me/agents (which returns
    Actor dicts) so display_name/actor_id/api_key_prefix accesses match
    the response shape. No space scoping: default_space_id lives on the
    human user, not on agents, so it can't be used to scope an agent
    list. In practice all sponsored agents on a fresh user are
    default-space-provisioned anyway.
    """
    resp = await client.get("/api/actors/me/agents")
    if resp.status_code != 200:
        print(f"Error: could not list agents ({resp.status_code})")
        raise SystemExit(1)
    agents = resp.json()
    return [
        a
        for a in agents
        if a.get("actor_type") == "agent"
        and (force or a.get("api_key_prefix") is None)
    ]


async def _rotate_keys(
    client: httpx.AsyncClient,
    agents: list[dict[str, Any]],
    force: bool = False,
) -> dict[str, dict[str, str]]:
    """Rotate keys for each agent in order. Returns {role_lower: {...}}."""
    adopted: dict[str, dict[str, str]] = {}
    headers = {"X-Force-Rotate": "true"} if force else {}
    for agent in agents:
        actor_id = agent["actor_id"]
        display_name = agent["display_name"]
        role_key = display_name.lower().replace(" ", "_")
        resp = await client.post(
            f"/api/actors/{actor_id}/rotate-key",
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            print(
                f"\nError: rotate-key failed for {display_name} "
                f"({resp.status_code})"
            )
            raise SystemExit(1)
        data = resp.json()
        adopted[role_key] = {
            "actor_id": actor_id,
            "api_key": data.get("api_key", ""),
            "display_name": display_name,
        }
        print(f"  {display_name:16s} ✓")
    return adopted


def _write_actors_json(
    *,
    space_id: str,
    space_name: str,
    api_url: str,
    adopted: dict[str, dict[str, str]],
) -> None:
    """Write .moot/actors.json with 0o600 perms under 0o700 parent."""
    moot_dir = Path(MOOT_DIR)
    moot_dir.mkdir(exist_ok=True)
    os.chmod(moot_dir, 0o700)

    content = {
        "space_id": space_id,
        "space_name": space_name,
        "api_url": api_url,
        "actors": adopted,
    }
    actors_path = Path(ACTORS_JSON)
    actors_path.write_text(json.dumps(content, indent=2))
    os.chmod(actors_path, 0o600)


def _write_moot_toml_from_adopted(
    *,
    adopted: dict[str, dict[str, str]],
    api_url: str,
    space_id: str | None = None,
    force: bool = False,
) -> None:
    """Generate moot.toml from adopted team data (D-TOML).

    If moot.toml exists, refuse to overwrite unless `force=True`. Print the
    skip explicitly so a user re-running `moot init` (without --force) can see
    that the existing toml was preserved — silent skip surprised users who
    expected the agent list to update after a key rotation.
    """
    toml_path = Path("moot.toml")
    if toml_path.exists() and not force:
        print(
            f"Skipped moot.toml              (exists; "
            f"re-run with --force to overwrite)"
        )
        return
    team_name = _infer_team_template(list(adopted.keys()))
    profile = TeamProfile(
        name=team_name,
        description="Adopted from default space",
        version="1.0",
        origin="moot-init-adoption",
    )
    for role_key, info in adopted.items():
        profile.roles.append(
            RoleProfile(
                name=role_key,
                display_name=info["display_name"],
                harness="claude-code",
            )
        )
    content = generate_moot_toml(profile, api_url, space_id=space_id)
    toml_path.write_text(content)
    print(f"Wrote moot.toml                ({len(adopted)} roles, template={team_name})")


def _infer_team_template(roles: list[str]) -> str:
    """Infer team template name from the adopted role set (D9)."""
    lower = {r.lower() for r in roles}
    if {"product", "spec", "implementation", "qa", "librarian"} <= lower:
        return "loop-5"
    if {"product", "spec", "implementation", "qa"} <= lower:
        return "loop-4"
    return "custom"


def _update_gitignore() -> None:
    """Append .moot/ (and legacy entries) to .gitignore."""
    gitignore = Path(".gitignore")
    existing = gitignore.read_text() if gitignore.exists() else ""
    additions = [e for e in GITIGNORE_ENTRIES if e not in existing]
    if additions:
        with open(gitignore, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write("# moot\n")
            for entry in additions:
                f.write(f"{entry}\n")
        print(f"Updated .gitignore             ({len(additions)} entries added)")


def _install_bundles(
    *,
    adopted: dict[str, dict[str, str]],
    space_id: str,
    space_name: str,
    api_url: str,
    overwrite: bool,
) -> dict[str, list[str]]:
    """Install skills, CLAUDE.md, devcontainer. Returns conflict map."""
    conflicts: dict[str, list[str]] = {"skills": [], "claude_md": [], "devcontainer": []}

    print("\nInstalling .claude/skills/:")
    for skill in BUNDLED_SKILLS:
        target_dir = Path(f".claude/skills/{skill}")
        src_dir = SKILLS_TEMPLATE_DIR / skill
        if target_dir.is_dir() and not overwrite:
            staged = Path(f"{MOOT_DIR}/suggested-skills/{skill}")
            staged.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_dir / "SKILL.md", staged / "SKILL.md")
            conflicts["skills"].append(skill)
            print(f"  {skill + '/':24s} ⚠ exists — staged at .moot/suggested-skills/{skill}/")
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_dir / "SKILL.md", target_dir / "SKILL.md")
            print(f"  {skill + '/':24s} ✓ installed")

    claude_path = Path("CLAUDE.md")
    placeholders = {
        "{project_name}": Path.cwd().name,
        "{space_id}": space_id,
        "{space_name}": space_name,
        "{team_template}": _infer_team_template(list(adopted.keys())),
        "{api_url}": api_url,
    }
    template_text = CLAUDE_MD_TEMPLATE.read_text()
    for k, v in placeholders.items():
        template_text = template_text.replace(k, v)

    if claude_path.exists() and not overwrite:
        staged = Path(f"{MOOT_DIR}/suggested-CLAUDE.md")
        staged.write_text(template_text)
        conflicts["claude_md"].append("CLAUDE.md")
        print("\nCLAUDE.md already exists — staged at .moot/suggested-CLAUDE.md")
    else:
        claude_path.write_text(template_text)
        print(
            f"\nInstalling CLAUDE.md           "
            f"(parameterized: project_name → {placeholders['{project_name}']})"
        )

    devcontainer_dir = Path(".devcontainer")
    src_devcontainer = DEVCONTAINER_TEMPLATE_DIR
    if devcontainer_dir.exists() and not overwrite:
        staged = Path(f"{MOOT_DIR}/suggested-devcontainer")
        staged.mkdir(parents=True, exist_ok=True)
        for src_file in src_devcontainer.iterdir():
            dest = staged / src_file.name
            shutil.copy2(src_file, dest)
            if src_file.suffix == ".sh":
                dest.chmod(
                    dest.stat().st_mode
                    | stat.S_IEXEC
                    | stat.S_IXGRP
                    | stat.S_IXOTH
                )
        conflicts["devcontainer"].append(".devcontainer/")
        print(".devcontainer/ already exists — staged at .moot/suggested-devcontainer/")
    else:
        devcontainer_dir.mkdir(exist_ok=True)
        for src_file in src_devcontainer.iterdir():
            dest = devcontainer_dir / src_file.name
            shutil.copy2(src_file, dest)
            if src_file.suffix == ".sh":
                dest.chmod(
                    dest.stat().st_mode
                    | stat.S_IEXEC
                    | stat.S_IXGRP
                    | stat.S_IXOTH
                )
        print(
            f"Installing .devcontainer/      "
            f"({len(list(devcontainer_dir.iterdir()))} files)"
        )

    return conflicts


def _write_init_report(
    *,
    space_id: str,
    space_name: str,
    api_url: str,
    adopted: dict[str, dict[str, str]],
    conflicts: dict[str, list[str]],
) -> None:
    """Write .moot/init-report.md (D-REPORT)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# moot init report",
        "",
        f"Generated {now}.",
        f"Default space: {space_id} ({space_name})",
        f"Backend: {api_url}",
        "",
        "## Mechanical setup (done)",
        "",
        f"- Rotated keys for {len(adopted)} agents: "
        f"{', '.join(a['display_name'] for a in adopted.values())}",
        f"- Wrote `{ACTORS_JSON}` (chmod 600)",
        "- Updated `.gitignore` with `.moot/` entry",
        "",
        "## Files ready to use directly",
        "",
    ]
    installed_skills = [s for s in BUNDLED_SKILLS if s not in conflicts["skills"]]
    for skill in installed_skills:
        lines.append(f"- `.claude/skills/{skill}/SKILL.md`")
    if not conflicts["claude_md"]:
        lines.append("- `CLAUDE.md`")
    if not conflicts["devcontainer"]:
        lines.append("- `.devcontainer/`")

    has_conflicts = any(conflicts.values())
    if has_conflicts:
        lines += [
            "",
            "## Files that need your agent's judgment (staged under .moot/suggested-*/)",
            "",
        ]
        if conflicts["claude_md"]:
            lines += [
                "### `.moot/suggested-CLAUDE.md`",
                "",
                "Your existing `CLAUDE.md` describes your project. The suggestion adds "
                "Moot-specific workflow discipline. Ask your agent to pick what to "
                "merge, what to put in a separate `.claude/MOOT.md`, and what to skip.",
                "",
            ]
        for skill in conflicts["skills"]:
            lines += [
                f"### `.moot/suggested-skills/{skill}/`",
                "",
                f"You already have a `.claude/skills/{skill}/` directory. The name "
                "collides but the content may not. Ask your agent to diff them and "
                "decide whether to merge or rename.",
                "",
            ]
        if conflicts["devcontainer"]:
            lines += [
                "### `.moot/suggested-devcontainer/`",
                "",
                "Your existing `.devcontainer/` reflects your dev environment. The "
                "suggestion is Moot's default devcontainer for running agents. Ask "
                "your agent whether to integrate.",
                "",
            ]

    lines += [
        "## Next step",
        "",
        (
            "Once your agent has reviewed any staged suggestions above, "
            "run `moot up` to bring your agent team online."
            if has_conflicts
            else "Run `moot up` to bring your agent team online."
        ),
        "",
    ]

    report_path = Path(f"{MOOT_DIR}/init-report.md")
    report_path.write_text("\n".join(lines))


async def _update_suggestions_only() -> None:
    """`moot init --update-suggestions`: refresh .moot/suggested-*/ only."""
    actors_path = Path(ACTORS_JSON)
    if not actors_path.exists():
        print(f"Error: {ACTORS_JSON} not found. Run `moot init` first.")
        raise SystemExit(1)
    data = json.loads(actors_path.read_text())
    conflicts = _install_bundles(
        adopted=data.get("actors", {}),
        space_id=data.get("space_id", ""),
        space_name=data.get("space_name", ""),
        api_url=data.get("api_url", ""),
        overwrite=False,
    )
    _write_init_report(
        space_id=data.get("space_id", ""),
        space_name=data.get("space_name", ""),
        api_url=data.get("api_url", ""),
        adopted=data.get("actors", {}),
        conflicts=conflicts,
    )
    print("\nDone. Staged suggestions refreshed.")


def _prompt_or_exit(prompt: str) -> None:
    """Print prompt, read one line; exit 0 if response is not y/yes."""
    try:
        response = input(prompt).strip().lower()
    except EOFError:
        response = ""
    if response not in ("y", "yes"):
        print("Aborted.")
        raise SystemExit(0)
