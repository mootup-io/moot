"""Unit tests for moot.lifecycle — mock the devcontainer module boundary."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest


@pytest.fixture
def patch_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import moot.lifecycle as lc

    class FakeAgent:
        def __init__(self, role: str) -> None:
            self.role = role
            self.startup_prompt = ""

    class FakeConfig:
        def __init__(self) -> None:
            self.agents = {"spec": FakeAgent("spec")}
            self.roles = ["spec"]

    monkeypatch.setattr(lc, "find_config", lambda: FakeConfig())
    monkeypatch.chdir(tmp_path)


def test_cmd_status_no_container(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: None)
    lc.cmd_status()
    out = capsys.readouterr().out
    assert "STOPPED" in out
    assert "(none)" in out


def test_cmd_status_with_container(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: "cidAAAAAAAAAAAA")
    # _session_exists is imported from moot.launch and calls moot.launch.exec_capture,
    # not lc.exec_capture. Patch it directly on lc.
    monkeypatch.setattr(lc, "_session_exists", lambda cid, role: True)
    lc.cmd_status()
    out = capsys.readouterr().out
    # [:12] of "cidAAAAAAAAAAAA" = "cidAAAAAAAAA" (3 + 9 = 12 chars)
    assert "Container: cidAAAAAAAAA" in out
    assert "moot-spec" in out
    assert "RUNNING" in out


def test_cmd_compact_sends_compact(
    monkeypatch: pytest.MonkeyPatch, patch_config: None
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: "cidCompact")
    monkeypatch.setattr(lc, "_session_exists", lambda cid, role: True)
    calls: list[list[str]] = []

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        calls.append(args)
        return (0, "", "")

    monkeypatch.setattr(lc, "exec_capture", fake_exec_capture)

    ns = argparse.Namespace(role="spec")
    lc.cmd_compact(ns)

    send_keys = [c for c in calls if c[:2] == ["tmux", "send-keys"]]
    assert send_keys == [
        ["tmux", "send-keys", "-t", "moot-spec", "/compact", "Enter"]
    ]


def test_cmd_attach_missing_container(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: None)
    ns = argparse.Namespace(role="spec")
    with pytest.raises(SystemExit) as exc:
        lc.cmd_attach(ns)
    assert exc.value.code == 1
    assert "No devcontainer running" in capsys.readouterr().out


def test_cmd_attach_missing_session(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: "cidAttach")
    # _session_exists is imported from moot.launch; patch on lc directly.
    monkeypatch.setattr(lc, "_session_exists", lambda cid, role: False)

    def boom(cid: str, args: list[str]) -> None:
        raise AssertionError("should not reach exec_interactive")

    monkeypatch.setattr(lc, "exec_interactive", boom)

    ns = argparse.Namespace(role="spec")
    with pytest.raises(SystemExit) as exc:
        lc.cmd_attach(ns)
    assert exc.value.code == 1
    assert "not running" in capsys.readouterr().out
