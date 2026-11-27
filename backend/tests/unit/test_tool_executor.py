from unittest.mock import AsyncMock

import app.agent.tool_executor as tool_executor
import pytest
from langchain_core.messages import AIMessage


def make_state(tool_calls):
    return {
        "execution_id": "execution-1",
        "messages": [AIMessage(content="", tool_calls=tool_calls)],
        "memory_summary": None,
        "iteration_count": 1,
        "execution_status": "running",
        "pending_approval": None,
        "pending_clarification": None,
    }


def make_tool_call(name, call_id, args):
    return {
        "name": name,
        "id": call_id,
        "args": args,
        "type": "tool_call",
    }


@pytest.mark.asyncio
async def test_tool_calls_execute_sequentially_and_preserve_ids(monkeypatch):
    execution_order = []

    async def fake_execute(tool, arguments, config):
        execution_order.append(arguments["value"])
        return {"result": arguments["value"]}

    monkeypatch.setattr(
        tool_executor,
        "TOOLS_BY_NAME",
        {"first_tool": object(), "second_tool": object()},
    )
    monkeypatch.setattr(
        tool_executor,
        "_execute_regular_tool",
        fake_execute,
    )

    state = make_state([
        make_tool_call("first_tool", "call-1", {"value": 1}),
        make_tool_call("second_tool", "call-2", {"value": 2}),
    ])

    result = await tool_executor.tool_executor_node(
        state,
        {"configurable": {"thread_id": "thread-1"}},
    )

    assert execution_order == [1, 2]
    assert [message.tool_call_id for message in result["messages"]] == [
        "call-1",
        "call-2",
    ]


@pytest.mark.asyncio
async def test_tool_failure_does_not_discard_other_results(monkeypatch):
    async def fake_execute(tool, arguments, config):
        if arguments["value"] == 2:
            raise ValueError("Invalid task data")

        return {"result": arguments["value"]}

    monkeypatch.setattr(
        tool_executor,
        "TOOLS_BY_NAME",
        {
            "first_tool": object(),
            "second_tool": object(),
            "third_tool": object(),
        },
    )
    monkeypatch.setattr(
        tool_executor,
        "_execute_regular_tool",
        fake_execute,
    )

    state = make_state([
        make_tool_call("first_tool", "call-1", {"value": 1}),
        make_tool_call("second_tool", "call-2", {"value": 2}),
        make_tool_call("third_tool", "call-3", {"value": 3}),
    ])

    result = await tool_executor.tool_executor_node(
        state,
        {"configurable": {"thread_id": "thread-1"}},
    )

    messages = result["messages"]

    assert len(messages) == 3
    assert messages[0].status != "error"
    assert messages[1].status == "error"
    assert "Invalid task data" in messages[1].content
    assert messages[2].status != "error"


@pytest.mark.asyncio
async def test_deletion_creates_approval_request(monkeypatch):
    pending = {
        "approval_id": "approval-1",
        "deletion_request_id": "deletion-1",
        "task_id": "task-1",
        "tool_call_id": "call-delete",
    }

    create_request = AsyncMock(
        return_value=('{"status": "pending_approval"}', pending)
    )

    monkeypatch.setattr(
        tool_executor,
        "TOOLS_BY_NAME",
        {"delete_task": object()},
    )
    monkeypatch.setattr(
        tool_executor,
        "_create_deletion_request",
        create_request,
    )

    state = make_state([
        make_tool_call(
            "delete_task",
            "call-delete",
            {"task_id": "task-1"},
        )
    ])

    result = await tool_executor.tool_executor_node(
        state,
        {"configurable": {"thread_id": "thread-1"}},
    )

    create_request.assert_awaited_once_with(
        {"task_id": "task-1"},
        thread_id="thread-1",
        execution_id="execution-1",
        tool_call_id="call-delete",
    )

    assert result["pending_approval"] == pending
    assert result["execution_status"] == "waiting_for_approval"
    assert result["messages"][0].tool_call_id == "call-delete"


@pytest.mark.asyncio
async def test_only_one_deletion_request_per_tool_call_batch(monkeypatch):
    pending = {
        "approval_id": "approval-1",
        "deletion_request_id": "deletion-1",
        "task_id": "task-1",
        "tool_call_id": "call-delete-1",
    }

    create_request = AsyncMock(
        return_value=('{"status": "pending_approval"}', pending)
    )

    monkeypatch.setattr(
        tool_executor,
        "TOOLS_BY_NAME",
        {"delete_task": object()},
    )
    monkeypatch.setattr(
        tool_executor,
        "_create_deletion_request",
        create_request,
    )

    state = make_state([
        make_tool_call(
            "delete_task",
            "call-delete-1",
            {"task_id": "task-1"},
        ),
        make_tool_call(
            "delete_task",
            "call-delete-2",
            {"task_id": "task-2"},
        ),
    ])

    result = await tool_executor.tool_executor_node(
        state,
        {"configurable": {"thread_id": "thread-1"}},
    )

    assert create_request.await_count == 1
    assert len(result["messages"]) == 2
    assert result["messages"][0].status != "error"
    assert result["messages"][1].status == "error"
    assert result["messages"][1].tool_call_id == "call-delete-2"
    assert result["pending_approval"] == pending
    assert result["execution_status"] == "waiting_for_approval"