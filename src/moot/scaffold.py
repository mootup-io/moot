from __future__ import annotations

import shutil
import stat
from pathlib import Path

from moot.team_profile import (
    TeamProfile,
    generate_claude_md,
    generate_moot_toml,
    resolve_template,
)

DEVCONTAINER_TEMPLATE_DIR = Path(__file__).parent / "templates" / "devcontainer"
DEFAULT_TEMPLATE = "loop-4"

GITIGNORE_ENTRIES = [".agents.json", ".env.local", ".worktrees/"]


def cmd_init(args: object) -> None:
    """Handle `moot init`."""
    api_url = getattr(args, "api_url", None) or "https://gemoot.com:8443"
    template_name = getattr(args, "template", None) or DEFAULT_TEMPLATE

    # Resolve and parse team template
    try:
        template_dir = resolve_template(template_name)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise SystemExit(1)

    profile = TeamProfile.from_toml(template_dir / "team.toml")
    print(f"Using template: {profile.name} ({profile.description})")

    # Create moot.toml if missing
    toml_path = Path("moot.toml")
    if not toml_path.exists():
        content = generate_moot_toml(profile, api_url)
        toml_path.write_text(content)
        print(f"Created {toml_path} ({len(profile.roles)} roles)")
    else:
        print(f"{toml_path} already exists -- skipping")

    # Create CLAUDE.md if missing
    claude_path = Path("CLAUDE.md")
    if not claude_path.exists():
        project_name = Path.cwd().name
        content = generate_claude_md(profile, template_dir, project_name)
        claude_path.write_text(content)
        print(f"Created {claude_path}")
    else:
        print(f"{claude_path} already exists -- skipping")

    # Update .gitignore
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
        print(f"Updated .gitignore ({len(additions)} entries added)")

    # Copy devcontainer template
    devcontainer_dir = Path(".devcontainer")
    if devcontainer_dir.exists():
        print(f"{devcontainer_dir}/ already exists -- skipping template copy")
    else:
        devcontainer_dir.mkdir()
        for src_file in DEVCONTAINER_TEMPLATE_DIR.iterdir():
            dest = devcontainer_dir / src_file.name
            shutil.copy2(src_file, dest)
            if src_file.suffix == ".sh":
                dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"Created {devcontainer_dir}/ ({len(list(devcontainer_dir.iterdir()))} files)")

    print("\nDone. Next steps:")
    print("  1. Edit CLAUDE.md -- fill in the TODO sections with your project details")
    print("  2. moot login --token <key>")
    print("  3. moot config provision")
    print("  4. moot up")
