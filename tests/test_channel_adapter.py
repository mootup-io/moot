import logging

import anyio
import pytest

from types import SimpleNamespace

from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from moot.adapters import channel_adapter, tmux_delivery
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


@pytest.mark.asyncio
async def test_tmux_delivery_sends_delayed_carriage_return(monkeypatch):
    calls = []
    sleeps = []

    async def fake_run_process(args, *, check=False):
        calls.append((args, check))
        return SimpleNamespace(returncode=0, stderr=b"")

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(tmux_delivery.anyio, "run_process", fake_run_process)
    monkeypatch.setattr(tmux_delivery.anyio, "sleep", fake_sleep)

    pushed = await tmux_delivery.send_channel_xml_via_tmux(
        "moot-kernel-leader",
        "hello\nthere",
        {"event_type": "mention"},
        enter_delay_seconds=0.25,
    )

    assert pushed is True
    assert sleeps == [0.25]
    assert calls == [
        (
            [
                "tmux",
                "send-keys",
                "-t",
                "moot-kernel-leader",
                "-l",
                '<channel event_type="mention">hello there</channel>',
            ],
            False,
        ),
        (["tmux", "send-keys", "-t", "moot-kernel-leader", "C-m"], False),
    ]


class _FakeTaskGroup:
    """Records start_soon calls without running the tasks."""

    def __init__(self) -> None:
        self.started: list[tuple] = []

    def start_soon(self, func, *args) -> None:
        self.started.append((func, args))


@pytest.mark.asyncio
async def test_tool_listing_contains_interval_contract(monkeypatch):
    a = make_adapter(monkeypatch)
    result = await a._server.request_handlers[ListToolsRequest](ListToolsRequest())
    tools = {tool.name: tool for tool in getattr(result.root, "tools")}

    assert {"set_interval", "clear_interval"} <= tools.keys()
    set_schema = tools["set_interval"].inputSchema
    assert set_schema["required"] == ["seconds", "prompt"]
    assert set_schema["properties"]["seconds"]["minimum"] == 60
    assert set_schema["properties"]["prompt"]["maxLength"] == 4096
    assert tools["clear_interval"].inputSchema["properties"] == {}


@pytest.mark.asyncio
async def test_set_interval_requires_running_adapter_and_starts_one_task(monkeypatch):
    a = make_adapter(monkeypatch)
    not_running = await a._handle_set_interval(60, "check the channel")
    assert not_running[0].text.startswith("Error:")
    assert a._interval_scope is None

    task_group = _FakeTaskGroup()
    a._task_group = task_group  # type: ignore[assignment]
    response = await a._server.request_handlers[CallToolRequest](
        CallToolRequest(
            params=CallToolRequestParams(
                name="set_interval",
                arguments={"seconds": 60, "prompt": "check the channel"},
            )
        )
    )
    result_text = getattr(response.root, "content")[0].text

    assert "every 60 seconds" in result_text
    assert a._interval_seconds == 60
    assert a._interval_prompt == "check the channel"
    assert len(task_group.started) == 1
    assert task_group.started[0][0] == a._interval_loop


@pytest.mark.asyncio
async def test_second_set_cancels_first_and_leaves_one_current_scope(monkeypatch):
    a = make_adapter(monkeypatch)
    task_group = _FakeTaskGroup()
    a._task_group = task_group  # type: ignore[assignment]
    await a._handle_set_interval(60, "old")
    first_scope = a._interval_scope

    await a._handle_set_interval(90, "new")

    assert first_scope is not None and first_scope.cancel_called
    assert a._interval_scope is not first_scope
    assert a._interval_seconds == 90
    assert a._interval_prompt == "new"
    assert len(task_group.started) == 2


@pytest.mark.asyncio
async def test_clear_interval_is_idempotent_and_clears_metadata(monkeypatch):
    a = make_adapter(monkeypatch)
    task_group = _FakeTaskGroup()
    a._task_group = task_group  # type: ignore[assignment]
    await a._handle_set_interval(60, "wake")
    scope = a._interval_scope

    cleared = await a._handle_clear_interval()
    cleared_again = await a._handle_clear_interval()

    assert scope is not None and scope.cancel_called
    assert "cleared" in cleared[0].text.lower()
    assert "no agent interval" in cleared_again[0].text.lower()
    assert a._interval_scope is None
    assert a._interval_seconds is None
    assert a._interval_prompt is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "seconds",
    [0, 59.99, float("nan"), float("inf"), "60", True, None],
)
async def test_invalid_seconds_reject_without_replacing(monkeypatch, seconds):
    a = make_adapter(monkeypatch)
    existing_scope = anyio.CancelScope()
    a._interval_scope = existing_scope
    a._interval_seconds = 60
    a._interval_prompt = "existing"

    result = await a._handle_set_interval(seconds, "new")

    assert result[0].text.startswith("Error:")
    assert a._interval_scope is existing_scope
    assert not existing_scope.cancel_called
    assert a._interval_prompt == "existing"


@pytest.mark.asyncio
async def test_prompt_bounds_reject_without_truncation_and_accept_4096(monkeypatch):
    a = make_adapter(monkeypatch)
    task_group = _FakeTaskGroup()
    a._task_group = task_group  # type: ignore[assignment]

    empty = await a._handle_set_interval(60, "")
    too_long = await a._handle_set_interval(60, "x" * 4097)
    non_string = await a._handle_set_interval(60, 42)
    accepted = await a._handle_set_interval(60, "x" * 4096)

    assert empty[0].text.startswith("Error:")
    assert too_long[0].text.startswith("Error:")
    assert non_string[0].text.startswith("Error:")
    assert "every 60 seconds" in accepted[0].text
    assert a._interval_prompt == "x" * 4096
