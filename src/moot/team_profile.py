"""TeamProfile -- data model for team.toml template files.

Parses a team.toml file into structured data used by the scaffold
generators to produce moot.toml, CLAUDE.md, and related files.
"""

from __future__ import annotations

import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RoleProfile:
    name: str
    display_name: str
    harness: str = "claude-code"
    responsibilities: str = ""
    startup_prompt: str = ""


@dataclass
class WorkflowProfile:
    description: str = ""
    pipeline: list[str] = field(default_factory=list)
    threads: dict[str, str] = field(default_factory=dict)
    handoff_method: str = "mention"
    handoff_includes: list[str] = field(default_factory=list)


@dataclass
class GitProfile:
    description: str = ""
    strategy: str = "worktree"
    feature_branch: str = "feat/{slug}"
    agent_branch: str = "{role}/{slug}"
    merge_to_main: str = "squash"
    ownership: dict[str, str] = field(default_factory=dict)


@dataclass
class ResourceProfile:
    description: str = ""
    owners: dict[str, str] = field(default_factory=dict)


@dataclass
class TeamProfile:
    name: str
    description: str = ""
    version: str = "1.0"
    origin: str = ""
    roles: list[RoleProfile] = field(default_factory=list)
    workflow: WorkflowProfile = field(default_factory=WorkflowProfile)
    git: GitProfile = field(default_factory=GitProfile)
    resources: ResourceProfile = field(default_factory=ResourceProfile)

    @classmethod
    def from_toml(cls, path: Path) -> TeamProfile:
        """Parse a team.toml file into a TeamProfile."""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        team = data.get("team", {})
        profile = cls(
            name=team.get("name", "unknown"),
            description=team.get("description", ""),
            version=team.get("version", "1.0"),
            origin=team.get("origin", ""),
        )

        # Parse roles (TOML array of tables)
        for role_data in data.get("roles", []):
            profile.roles.append(RoleProfile(
                name=role_data["name"],
                display_name=role_data.get("display_name", role_data["name"].title()),
                harness=role_data.get("harness", "claude-code"),
                responsibilities=role_data.get("responsibilities", "").strip(),
                startup_prompt=role_data.get("startup_prompt", "").strip(),
            ))

        # Parse workflow
        wf = data.get("workflow", {})
        profile.workflow = WorkflowProfile(
            description=wf.get("description", "").strip(),
            pipeline=wf.get("pipeline", []),
            threads=wf.get("threads", {}),
            handoff_method=wf.get("handoff", {}).get("method", "mention"),
            handoff_includes=wf.get("handoff", {}).get("includes", []),
        )

        # Parse git
        git = data.get("git", {})
        profile.git = GitProfile(
            description=git.get("description", "").strip(),
            strategy=git.get("strategy", "worktree"),
            feature_branch=git.get("feature_branch", "feat/{slug}"),
            agent_branch=git.get("agent_branch", "{role}/{slug}"),
            merge_to_main=git.get("merge_to_main", "squash"),
            ownership=git.get("ownership", {}),
        )

        # Parse resources
        res = data.get("resources", {})
        profile.resources = ResourceProfile(
            description=res.get("description", "").strip(),
            owners=res.get("owners", {}),
        )

        return profile


# -- Template resolver -------------------------------------------------------

TEAMS_DIR = Path(__file__).parent / "templates" / "teams"


def resolve_template(name_or_path: str) -> Path:
    """Resolve a template name or path to a directory containing team.toml.

    Resolution order:
    1. Local path (if it exists as a directory)
    2. Built-in template name (looked up in templates/teams/)

    Raises FileNotFoundError if the template or team.toml doesn't exist.
    """
    # Local path
    path = Path(name_or_path)
    if path.is_dir():
        toml_path = path / "team.toml"
        if not toml_path.exists():
            raise FileNotFoundError(f"No team.toml found in {path}")
        return path

    # Built-in template
    builtin = TEAMS_DIR / name_or_path
    if builtin.is_dir():
        toml_path = builtin / "team.toml"
        if not toml_path.exists():
            raise FileNotFoundError(f"Built-in template '{name_or_path}' has no team.toml")
        return builtin

    # List available templates for error message
    available = sorted(d.name for d in TEAMS_DIR.iterdir() if d.is_dir()) if TEAMS_DIR.exists() else []
    raise FileNotFoundError(
        f"Template '{name_or_path}' not found. "
        f"Available: {', '.join(available) or 'none'}"
    )


# -- Generators --------------------------------------------------------------


def generate_moot_toml(
    profile: TeamProfile, api_url: str, space_id: str | None = None
) -> str:
    """Generate moot.toml content from a TeamProfile.

    If `space_id` is provided (e.g., from `moot init` which already knows
    the user's default space), emit it as a real value. Otherwise, emit a
    commented placeholder so the user can set it later (via `moot config
    set space_id <id>` or by hand).
    """
    space_id_line = (
        f'space_id = "{space_id}"'
        if space_id
        else '# space_id = ""  # Set after creating a space'
    )
    lines = [
        "[convo]",
        f'api_url = "{api_url}"',
        f'template = "{profile.name}"',
        space_id_line,
        "",
    ]

    for role in profile.roles:
        lines.append(f"[agents.{role.name}]")
        lines.append(f'display_name = "{role.display_name}"')
        lines.append('profile = "devcontainer"')
        # Escape quotes in startup prompt, collapse to single line
        prompt = role.startup_prompt.replace("\n", " ").strip()
        prompt = prompt.replace('"', '\\"')
        lines.append(f'startup_prompt = "{prompt}"')
        lines.append("")

    # Use the first role's harness as default
    harness = profile.roles[0].harness if profile.roles else "claude-code"
    lines.append("[harness]")
    lines.append(f'type = "{harness}"')
    lines.append('permissions = "dangerously-skip"')
    lines.append("")

    return "\n".join(lines)


def generate_claude_md(profile: TeamProfile, template_dir: Path, project_name: str = "My Project") -> str:
    """Generate CLAUDE.md by filling placeholders in the template."""
    template_path = template_dir / "CLAUDE.md"
    if not template_path.exists():
        return _generate_minimal_claude_md(profile, project_name)

    template = template_path.read_text()

    replacements = {
        "project_name": project_name,
        "role_count": str(len(profile.roles)),
        "role_list": _format_role_list(profile.roles),
        "role_descriptions": _format_role_descriptions(profile.roles),
        "workflow_description": profile.workflow.description,
        "pipeline_diagram": _format_pipeline_diagram(profile.workflow.pipeline),
        "handoff_protocol": _format_handoff_protocol(profile.workflow),
        "threading_protocol": _format_threading_protocol(profile.workflow.threads),
        "git_description": _format_git_section(profile.git),
        "resource_ownership": _format_resource_ownership(profile.resources),
    }

    # Use str.format_map with a defaultdict to leave unknown placeholders intact
    safe = defaultdict(str, replacements)
    return template.format_map(safe)


def _format_role_list(roles: list[RoleProfile]) -> str:
    """Format: 'Product, Spec, Implementation, and QA'."""
    names = [f"**{r.display_name}**" for r in roles]
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + ", and " + names[-1]


def _format_role_descriptions(roles: list[RoleProfile]) -> str:
    """Generate markdown role descriptions."""
    parts = []
    for role in roles:
        parts.append(f"- **{role.display_name}** -- {role.responsibilities}")
    return "\n".join(parts)


def _format_pipeline_diagram(pipeline: list[str]) -> str:
    """Generate: Product --> Spec --> Implementation --> QA --> Product"""
    if not pipeline:
        return ""
    names = [p.title() for p in pipeline]
    # Close the loop
    names.append(names[0])
    return " --> ".join(names)


def _format_handoff_protocol(workflow: WorkflowProfile) -> str:
    """Generate handoff protocol section."""
    lines = [
        "Each handoff is a channel message **@mentioning the next agent by participant_id**.",
        f"Handoff method: {workflow.handoff_method}.",
        "",
        "Handoff messages include:",
    ]
    for item in workflow.handoff_includes:
        lines.append(f"- {item.capitalize()}")
    return "\n".join(lines)


def _format_threading_protocol(threads: dict[str, str]) -> str:
    """Generate threading protocol section."""
    if not threads:
        return "Use threaded conversations for organized discussion."
    lines = ["Three kinds of threads, distinguished by the root message prefix:", ""]
    for name, prefix in threads.items():
        display = name.replace("_", " ").title()
        lines.append(f"- **`{prefix}` threads** -- {display}")
    return "\n".join(lines)


def _format_git_section(git: GitProfile) -> str:
    """Generate git workflow section."""
    lines = [git.description, ""]
    lines.append(f"- Strategy: {git.strategy}")
    lines.append(f"- Feature branches: `{git.feature_branch}`")
    lines.append(f"- Agent branches: `{git.agent_branch}`")
    lines.append(f"- Merge to main: {git.merge_to_main}")
    if git.ownership:
        lines.append("")
        lines.append("**Ownership:**")
        for resource, owner in git.ownership.items():
            lines.append(f"- {resource.replace('_', ' ').title()}: {owner.title()}")
    return "\n".join(lines)


def _format_resource_ownership(resources: ResourceProfile) -> str:
    """Generate resource ownership table."""
    if not resources.owners:
        return resources.description
    lines = [resources.description, ""]
    lines.append("| Resource | Owner |")
    lines.append("|----------|-------|")
    for resource, owner in resources.owners.items():
        lines.append(f"| {resource.replace('_', ' ').title()} | {owner.title()} |")
    return "\n".join(lines)


def _generate_minimal_claude_md(profile: TeamProfile, project_name: str) -> str:
    """Fallback: generate a minimal CLAUDE.md without a template file."""
    return f"""# {project_name}

TODO: Describe your project.

## Tech stack

TODO: Language, frameworks, databases, build tools.

## Agent Workflow

{len(profile.roles)} agents collaborate on this project: {_format_role_list(profile.roles)}.

### Roles

{_format_role_descriptions(profile.roles)}

### Work Pipeline

{profile.workflow.description}

```
{_format_pipeline_diagram(profile.workflow.pipeline)}
```
"""
