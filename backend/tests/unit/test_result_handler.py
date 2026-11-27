import pytest
from app.agent.result_handler import result_handler_node
from langchain_core.messages import AIMessage, ToolMessage


def make_state(messages, pending_approval=None):
    return {
        "execution_id": "execution-1",
        "messages": messages,
        "memory_summary": None,
        "iteration_count": 1,
        "execution_status": (
            "waiting_for_approval" if pending_approval else "running"
        ),
        "pending_approval": pending_approval,
        "pending_clarification": None,
    }


def make_ai_message():
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "create_task",
                "args": {"title": "Task A"},
                "id": "call-1",
                "type": "tool_call",
            },
            {
                "name": "list_tasks",
                "args": {},
                "id": "call-2",
                "type": "tool_call",
            },
        ],
    )


def test_result_handler_accepts_matching_tool_results():
    state = make_state([
        make_ai_message(),
        ToolMessage(content="Created", tool_call_id="call-1"),
        ToolMessage(content="Listed", tool_call_id="call-2"),
    ])

    result = result_handler_node(state)

    assert result == {"execution_status": "running"}


def test_result_handler_preserves_waiting_for_approval():
    pending_approval = {
        "approval_id": "approval-1",
        "deletion_request_id": "deletion-1",
        "task_id": "task-1",
        "tool_call_id": "call-1",
    }

    ai_message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "delete_task",
                "args": {"task_id": "task-1"},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )

    state = make_state(
        [
            ai_message,
            ToolMessage(
                content="Pending approval",
                tool_call_id="call-1",
            ),
        ],
        pending_approval=pending_approval,
    )

    result = result_handler_node(state)

    assert result == {"execution_status": "waiting_for_approval"}


def test_result_handler_rejects_missing_tool_result():
    state = make_state([
        make_ai_message(),
        ToolMessage(content="Created", tool_call_id="call-1"),
    ])

    with pytest.raises(ValueError, match="Tool results do not match"):
        result_handler_node(state)


def test_result_handler_rejects_wrong_tool_result_order():
    state = make_state([
        make_ai_message(),
        ToolMessage(content="Listed", tool_call_id="call-2"),
        ToolMessage(content="Created", tool_call_id="call-1"),
    ])

    with pytest.raises(ValueError, match="Tool results do not match"):
        result_handler_node(state)