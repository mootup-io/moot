"""moot CLI — scaffold and run Moot agent teams."""
from __future__ import annotations

import argparse
import asyncio
import sys

from moot import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="moot",
        description="Scaffold and run Moot agent teams",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    # moot login
    login_p = sub.add_parser("login", help="Authenticate against mootup.io")
    login_p.add_argument(
        "--token",
        default=None,
        help="Personal access token (prompts interactively if omitted)",
    )
    login_p.add_argument("--api-url", default=None, help="Moot API URL")

    # moot init
    init_p = sub.add_parser(
        "init",
        help="Provision agents and install Moot workflow bundles",
    )
    init_p.add_argument(
        "--api-url", default=None, help="Moot API URL (overrides credential)"
    )
    init_p.add_argument(
        "--force",
        action="store_true",
        help="Rotate keys for already-adopted agents (destructive)",
    )
    init_p.add_argument(
        "--update-suggestions",
        action="store_true",
        help="Refresh .moot/suggested-*/ from bundled templates; no key rotation",
    )
    init_p.add_argument(
        "--adopt-fresh-install",
        action="store_true",
        help="Overwrite CLAUDE.md / .claude/skills/ / .devcontainer/ unconditionally",
    )
    init_p.add_argument(
        "--fresh",
        action="store_true",
        help="Legacy path: create new agents in a new tenant",
    )
    init_p.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip all confirmation prompts",
    )
    init_p.add_argument(
        "--roles", default=None, help="Comma-separated roles (--fresh only)"
    )
    init_p.add_argument(
        "--template", "-t",
        default=None,
        help="Team template name (--fresh only). Built-in: loop-3, loop-4, loop-4-observer, loop-4-parallel, loop-4-split-leader",
    )

    # moot config
    config_p = sub.add_parser("config", help="Configure agent team")
    config_sub = config_p.add_subparsers(dest="config_command")
    config_sub.add_parser("show", help="Print current config")
    set_p = config_sub.add_parser("set", help="Set a config value")
    set_p.add_argument("key")
    set_p.add_argument("value")
    prov_p = config_sub.add_parser("provision", help="Register actors")
    prov_p.add_argument(
        "--fresh",
        action="store_true",
        help="Create new agents in a new tenant (writes .moot/agents-fresh.json)",
    )
    focus_p = config_sub.add_parser("focus", help="Set focus space")
    focus_p.add_argument("space_id")

    # moot up / down
    up_p = sub.add_parser("up", help="Start all agents")
    up_p.add_argument("--only", default=None, help="Comma-separated roles")
    down_p = sub.add_parser("down", help="Stop agents")
    down_p.add_argument("role", nargs="?", help="Stop specific role")

    # moot exec
    exec_p = sub.add_parser("exec", help="Launch single agent")
    exec_p.add_argument("role")
    exec_p.add_argument("--prompt", default=None)

    # moot status / compact / attach
    sub.add_parser("status", help="Show running agents")
    compact_p = sub.add_parser("compact", help="Compact agent context")
    compact_p.add_argument("role", nargs="?", help="Compact specific role")
    attach_p = sub.add_parser("attach", help="Attach to agent tmux session")
    attach_p.add_argument("role")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch
    if args.command == "login":
        from moot.auth import cmd_login
        asyncio.run(cmd_login(args))
    elif args.command == "init":
        from moot.scaffold import cmd_init
        cmd_init(args)
    elif args.command == "config":
        from moot.config import cmd_config
        if args.config_command == "provision":
            from moot.provision import cmd_provision
            asyncio.run(cmd_provision(args))
        else:
            cmd_config(args)
    elif args.command == "up":
        from moot.launch import cmd_up
        cmd_up(args)
    elif args.command == "down":
        from moot.launch import cmd_down
        cmd_down(args)
    elif args.command == "exec":
        from moot.launch import cmd_exec
        cmd_exec(args)
    elif args.command == "status":
        from moot.lifecycle import cmd_status
        cmd_status()
    elif args.command == "compact":
        from moot.lifecycle import cmd_compact
        cmd_compact(args)
    elif args.command == "attach":
        from moot.lifecycle import cmd_attach
        cmd_attach(args)
