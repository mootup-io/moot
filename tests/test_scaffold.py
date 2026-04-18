"""Tests for moot init — adoption flow."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
import respx
from httpx import Response

from moot.scaffold import cmd_init
from moot.config import ACTORS_JSON


def _actor_dict(
    *,
    actor_id: str,
    display_name: str,
    actor_type: str = "agent",
    sponsor_id: str | None = "usr_test_1",
    api_key_prefix: str | None = None,
    default_space_id: str | None = None,
    is_connected: bool | None = False,
) -> dict:
    """Return a full Actor.model_dump() shape for respx mocks.

    Field order and defaults match backend/core/models/models.py::Actor.
    """
    return {
        "actor_id": actor_id,
        "display_name": display_name,
        "actor_type": actor_type,
        "sponsor_id": sponsor_id,
        "tenant_id": "ten_test_1",
        "is_admin": False,
        "email": None,
        "agent_profile": None,
        "api_key_prefix": api_key_prefix,
        "default_space_id": default_space_id,
        "is_connected": is_connected,
        "focus_space_id": None,
        "metadata": None,
        "last_seen_at": None,
        "created_at": "2026-04-18T00:00:00+00:00",
        "updated_at": "2026-04-18T00:00:00+00:00",
    }


def _stub_backend(respx_mock: respx.Router, api_url: str) -> None:
    """Stub the 3-call happy-path flow (post-Run-W scaffold).

    Endpoints (all anchored to convo OAS b6f6d13):
      GET  /api/actors/me                    — Actor.model_dump()
      GET  /api/spaces/{space_id}            — 404 (no GET handler; scaffold falls back to space_id)
      GET  /api/actors/me/agents             — list[Actor.model_dump()]
      POST /api/actors/{actor_id}/rotate-key — Actor.model_dump() + api_key
    """
    respx_mock.get(f"{api_url}/api/actors/me").mock(
        return_value=Response(
            200,
            json=_actor_dict(
                actor_id="usr_user_1",
                display_name="Test User",
                actor_type="human",
                sponsor_id=None,
                default_space_id="spc_test_1",
            ),
        )
    )
    # GET /api/spaces/{id} is not implemented; scaffold swallows the 404.
    respx_mock.get(f"{api_url}/api/spaces/spc_test_1").mock(
        return_value=Response(404, json={"detail": "Not found"})
    )
    respx_mock.get(f"{api_url}/api/actors/me/agents").mock(
        return_value=Response(
            200,
            json=[
                _actor_dict(
                    actor_id=f"agt_{role.lower()}_1",
                    display_name=role,
                )
                for role in ("Product", "Spec", "Implementation", "QA")
            ],
        )
    )
    for role in ("product", "spec", "implementation", "qa"):
        respx_mock.post(
            f"{api_url}/api/actors/agt_{role}_1/rotate-key"
        ).mock(
            return_value=Response(
                200,
                json={
                    **_actor_dict(
                        actor_id=f"agt_{role}_1",
                        display_name=role.capitalize(),
                        api_key_prefix="convo_ke",
                    ),
                    "api_key": f"convo_key_live_{role}",
                },
            )
        )


def _stub_credential(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import moot.auth as auth_mod

    cred_dir = tmp_path / ".moot-home"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)
    auth_mod.store_credential(
        token="mootup_pat_test",
        api_url="https://mootup.io",
        user_id="agt_user_1",
    )


class _Args:
    force = False
    update_suggestions = False
    adopt_fresh_install = False
    fresh = False
    yes = False
    api_url = None
    roles = None
    template = None


@respx.mock
def test_init_greenfield_rotates_and_installs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Greenfield moot init: HTTP flow, skills + CLAUDE.md + devcontainer installed, actors.json written."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    _stub_credential(monkeypatch, tmp_path)
    _stub_backend(respx.mock, "https://mootup.io")

    cmd_init(_Args())

    actors_path = tmp_path / ACTORS_JSON
    assert actors_path.exists()
    assert stat.S_IMODE(os.stat(actors_path).st_mode) == 0o600
    moot_dir = tmp_path / ".moot"
    assert stat.S_IMODE(os.stat(moot_dir).st_mode) == 0o700

    data = json.loads(actors_path.read_text())
    assert data["space_id"] == "spc_test_1"
    assert data["api_url"] == "https://mootup.io"
    assert set(data["actors"].keys()) == {
        "product",
        "spec",
        "implementation",
        "qa",
    }
    assert data["actors"]["product"]["api_key"] == "convo_key_live_product"
    assert data["actors"]["product"]["display_name"] == "Product"

    assert (tmp_path / "moot.toml").exists()
    for skill in (
        "product-workflow",
        "spec-checklist",
        "leader-workflow",
        "librarian-workflow",
        "handoff",
        "verify",
        "doc-curation",
    ):
        assert (tmp_path / ".claude" / "skills" / skill / "SKILL.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".devcontainer" / "devcontainer.json").exists()
    assert (tmp_path / ".gitignore").exists()
    assert ".moot/" in (tmp_path / ".gitignore").read_text()
    assert (tmp_path / ".moot" / "init-report.md").exists()
    report = (tmp_path / ".moot" / "init-report.md").read_text()
    assert "Mechanical setup (done)" in report


@respx.mock
def test_init_conflict_stages_claude_md(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-existing CLAUDE.md is preserved; bundled template is staged."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    claude_path = tmp_path / "CLAUDE.md"
    claude_path.write_text("# My Project\nUser content.\n")

    _stub_credential(monkeypatch, tmp_path)
    _stub_backend(respx.mock, "https://mootup.io")

    cmd_init(_Args())

    assert claude_path.read_text() == "# My Project\nUser content.\n"
    staged = tmp_path / ".moot" / "suggested-CLAUDE.md"
    assert staged.exists()
    assert "{project_name}" not in staged.read_text()
    # Non-colliding skills still install directly
    assert (tmp_path / ".claude" / "skills" / "handoff" / "SKILL.md").exists()
    report = (tmp_path / ".moot" / "init-report.md").read_text()
    assert ".moot/suggested-CLAUDE.md" in report


@respx.mock
def test_init_conflict_stages_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-existing skill dir is preserved; bundled skill is staged."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    user_skill_dir = tmp_path / ".claude" / "skills" / "spec-checklist"
    user_skill_dir.mkdir(parents=True)
    user_skill_md = user_skill_dir / "SKILL.md"
    user_skill_md.write_text("# user spec-checklist\n")

    _stub_credential(monkeypatch, tmp_path)
    _stub_backend(respx.mock, "https://mootup.io")

    cmd_init(_Args())

    assert user_skill_md.read_text() == "# user spec-checklist\n"
    staged = (
        tmp_path / ".moot" / "suggested-skills" / "spec-checklist" / "SKILL.md"
    )
    assert staged.exists()
    # Non-colliding skill lands directly
    assert (tmp_path / ".claude" / "skills" / "handoff" / "SKILL.md").exists()
    report = (tmp_path / ".moot" / "init-report.md").read_text()
    assert "spec-checklist" in report


@respx.mock
def test_init_conflict_stages_devcontainer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-existing .devcontainer/ is preserved; bundled files are staged."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    user_devcontainer = tmp_path / ".devcontainer"
    user_devcontainer.mkdir()
    user_file = user_devcontainer / "devcontainer.json"
    user_file.write_text("{\"name\":\"user\"}")

    _stub_credential(monkeypatch, tmp_path)
    _stub_backend(respx.mock, "https://mootup.io")

    cmd_init(_Args())

    assert user_file.read_text() == "{\"name\":\"user\"}"
    staged = tmp_path / ".moot" / "suggested-devcontainer"
    assert staged.exists()
    assert (staged / "devcontainer.json").exists()
    report = (tmp_path / ".moot" / "init-report.md").read_text()
    assert ".devcontainer/" in report


def test_init_refuses_without_force_when_actors_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-existing actors.json triggers refuse-without-force."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    moot_dir = tmp_path / ".moot"
    moot_dir.mkdir()
    actors_path = moot_dir / "actors.json"
    original_content = '{"existing":"content"}'
    actors_path.write_text(original_content)

    _stub_credential(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        cmd_init(_Args())
    assert exc_info.value.code == 1
    assert actors_path.read_text() == original_content


@respx.mock
def test_init_force_rotates_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--force rotates keys on a pre-existing install."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    moot_dir = tmp_path / ".moot"
    moot_dir.mkdir()
    (moot_dir / "actors.json").write_text('{"stale":"data"}')

    _stub_credential(monkeypatch, tmp_path)
    _stub_backend(respx.mock, "https://mootup.io")

    class ForceArgs(_Args):
        force = True
        yes = True

    cmd_init(ForceArgs())

    data = json.loads((moot_dir / "actors.json").read_text())
    assert "actors" in data
    assert data["actors"]["product"]["api_key"] == "convo_key_live_product"

    # Verify X-Force-Rotate header was sent
    rotate_call = respx.mock.routes[3].calls.last
    assert rotate_call.request.headers.get("x-force-rotate") == "true"


@respx.mock
def test_init_update_suggestions_no_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--update-suggestions reads existing actors.json, no HTTP calls."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    moot_dir = tmp_path / ".moot"
    moot_dir.mkdir()
    actors_content = {
        "space_id": "spc_test_1",
        "space_name": "Test Space",
        "api_url": "https://mootup.io",
        "actors": {
            "product": {
                "actor_id": "agt_product_1",
                "api_key": "convo_key_live_product",
                "display_name": "Product",
            },
            "spec": {
                "actor_id": "agt_spec_1",
                "api_key": "convo_key_live_spec",
                "display_name": "Spec",
            },
            "implementation": {
                "actor_id": "agt_implementation_1",
                "api_key": "convo_key_live_implementation",
                "display_name": "Implementation",
            },
            "qa": {
                "actor_id": "agt_qa_1",
                "api_key": "convo_key_live_qa",
                "display_name": "QA",
            },
        },
    }
    original_serialized = json.dumps(actors_content, indent=2)
    (moot_dir / "actors.json").write_text(original_serialized)
    claude_path = tmp_path / "CLAUDE.md"
    claude_path.write_text("# User content\n")

    _stub_credential(monkeypatch, tmp_path)

    class UpdateArgs(_Args):
        update_suggestions = True

    cmd_init(UpdateArgs())

    assert (moot_dir / "actors.json").read_text() == original_serialized
    staged = moot_dir / "suggested-CLAUDE.md"
    assert staged.exists()
    assert (moot_dir / "init-report.md").exists()
    assert len(respx.mock.calls) == 0


@respx.mock
def test_init_adopt_fresh_install_overwrites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--adopt-fresh-install --yes overwrites user CLAUDE.md unconditionally."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    claude_path = tmp_path / "CLAUDE.md"
    claude_path.write_text("# User content to be lost\n")

    _stub_credential(monkeypatch, tmp_path)
    _stub_backend(respx.mock, "https://mootup.io")

    class AdoptArgs(_Args):
        adopt_fresh_install = True
        yes = True

    cmd_init(AdoptArgs())

    # User content gone; bundled template installed
    assert "User content to be lost" not in claude_path.read_text()
    # No staging under suggested
    assert not (tmp_path / ".moot" / "suggested-CLAUDE.md").exists()
    assert (tmp_path / ".moot" / "actors.json").exists()


@respx.mock
def test_init_rotate_key_failure_does_not_persist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If rotate-key fails, .moot/actors.json is NOT written."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    _stub_credential(monkeypatch, tmp_path)

    api_url = "https://mootup.io"
    respx.mock.get(f"{api_url}/api/actors/me").mock(
        return_value=Response(
            200,
            json=_actor_dict(
                actor_id="usr_user_1",
                display_name="Test User",
                actor_type="human",
                sponsor_id=None,
                default_space_id="spc_test_1",
            ),
        )
    )
    respx.mock.get(f"{api_url}/api/spaces/spc_test_1").mock(
        return_value=Response(404, json={"detail": "Not found"})
    )
    respx.mock.get(f"{api_url}/api/actors/me/agents").mock(
        return_value=Response(
            200,
            json=[
                _actor_dict(
                    actor_id="agt_product_1",
                    display_name="Product",
                )
            ],
        )
    )
    respx.mock.post(f"{api_url}/api/actors/agt_product_1/rotate-key").mock(
        return_value=Response(500, json={"error": "boom"})
    )

    with pytest.raises(SystemExit) as exc_info:
        cmd_init(_Args())
    assert exc_info.value.code == 1
    assert not (tmp_path / ".moot" / "actors.json").exists()


@respx.mock
def test_init_warns_on_non_git_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-git repo emits a warning but proceeds."""
    monkeypatch.chdir(tmp_path)
    _stub_credential(monkeypatch, tmp_path)
    _stub_backend(respx.mock, "https://mootup.io")

    cmd_init(_Args())

    captured = capsys.readouterr()
    assert "doesn't look like a git repository" in captured.out
    assert (tmp_path / ".moot" / "actors.json").exists()


@respx.mock
def test_init_placeholder_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLAUDE.md has no unfilled placeholders after a successful init."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    _stub_credential(monkeypatch, tmp_path)
    _stub_backend(respx.mock, "https://mootup.io")

    cmd_init(_Args())

    content = (tmp_path / "CLAUDE.md").read_text()
    for placeholder in (
        "{project_name}",
        "{space_id}",
        "{space_name}",
        "{team_template}",
        "{api_url}",
    ):
        assert placeholder not in content, (
            f"Unfilled placeholder {placeholder} in CLAUDE.md"
        )


def test_infer_team_template() -> None:
    """_infer_team_template picks the right template name."""
    from moot.scaffold import _infer_team_template

    assert (
        _infer_team_template(["product", "spec", "implementation", "qa"])
        == "loop-4"
    )
    assert (
        _infer_team_template(
            ["product", "spec", "implementation", "qa", "librarian"]
        )
        == "loop-5"
    )
    assert _infer_team_template(["a", "b"]) == "custom"


def test_launch_includes_channel_flag() -> None:
    """cmd_exec() claude command includes --dangerously-load-development-channels."""
    import inspect
    from moot.launch import cmd_exec

    source = inspect.getsource(cmd_exec)
    assert "--dangerously-load-development-channels" in source
    assert "server:convo-channel" in source
