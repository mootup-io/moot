import logging

import pytest

from moot.adapters import channel_adapter
from moot.adapters.channel_adapter import ChannelAdapter
from moot.adapters.notify_runner import default_tmux_session


def make_adapter(
    monkeypatch: pytest.MonkeyPatch, *, role: str = "kernel-leader"
) -> ChannelAdapter:
    monkeypatch.setenv("CONVO_ROLE", role)
    return ChannelAdapter(
        api_url="http://localhost:8000", agent_id=role, agent_name=role
    )


@pytest.mark.asyncio
async def test_channel_adapter_claude_pane_uses_claude_channel(monkeypatch):
    adapter = make_adapter(monkeypatch)
    monkeypatch.setattr(adapter, "_pane_command", lambda: "claude")

    claude_calls = []

    async def fake_claude(content, meta):
        claude_calls.append((content, meta))
        return True

    async def fake_tmux(*args, **kwargs):
        raise AssertionError("tmux fallback should not be used for Claude")

    monkeypatch.setattr(adapter, "_push_claude_channel_notification", fake_claude)
    monkeypatch.setattr(channel_adapter, "send_channel_xml_via_tmux", fake_tmux)

    await adapter._push_notification("hello", {"event_type": "mention"})
    await adapter.stop()

    assert claude_calls == [("hello", {"event_type": "mention"})]


@pytest.mark.asyncio
@pytest.mark.parametrize("pane_command", ["codex", "cursor", "aider"])
async def test_channel_adapter_non_claude_panes_use_tmux(monkeypatch, pane_command):
    adapter = make_adapter(monkeypatch)
    monkeypatch.setattr(adapter, "_pane_command", lambda: pane_command)

    tmux_calls = []

    async def fake_claude(*args, **kwargs):
        raise AssertionError("Claude channel should not be used for non-Claude panes")

    async def fake_tmux(session, content, meta, *, log_success=True):
        tmux_calls.append((session, content, meta, log_success))
        return True

    monkeypatch.setattr(adapter, "_push_claude_channel_notification", fake_claude)
    monkeypatch.setattr(channel_adapter, "send_channel_xml_via_tmux", fake_tmux)

    await adapter._push_notification("hello", {"event_type": "mention"})
    await adapter.stop()

    assert tmux_calls == [
        ("moot-kernel-leader", "hello", {"event_type": "mention"}, False)
    ]


def test_channel_adapter_tmux_session_override(monkeypatch):
    monkeypatch.setenv("CONVO_ROLE", "kernel-leader")
    monkeypatch.setenv("CONVO_TMUX_SESSION", "custom-session")

    adapter = ChannelAdapter(
        api_url="http://localhost:8000",
        agent_id="kernel-leader",
        agent_name="kernel-leader",
    )

    assert adapter._tmux_session == "custom-session"


def test_notify_runner_default_tmux_session(monkeypatch):
    monkeypatch.delenv("CONVO_TMUX_SESSION", raising=False)
    assert default_tmux_session("kernel-leader") == "moot-kernel-leader"
    assert default_tmux_session("kernel-leader", "explicit") == "explicit"


def test_notify_runner_tmux_session_override(monkeypatch):
    monkeypatch.setenv("CONVO_TMUX_SESSION", "override-session")
    assert default_tmux_session("kernel-leader") == "override-session"


@pytest.mark.asyncio
async def test_channel_adapter_tmux_failure_logs_failure_not_success(
    monkeypatch, caplog
):
    adapter = make_adapter(monkeypatch)
    monkeypatch.setattr(adapter, "_pane_command", lambda: "codex")

    async def fake_tmux(session, content, meta, *, log_success=True):
        return False

    monkeypatch.setattr(channel_adapter, "send_channel_xml_via_tmux", fake_tmux)

    with caplog.at_level(logging.INFO, logger="convo.channel"):
        await adapter._push_notification("hello", {"event_type": "mention"})
    await adapter.stop()

    messages = [record.getMessage() for record in caplog.records]
    assert any("Selected tmux notification backend" in message for message in messages)
    assert any(
        "Failed to push mention notification via tmux" in message
        for message in messages
    )
    assert not any(
        "Pushed mention notification via tmux" in message for message in messages
    )
