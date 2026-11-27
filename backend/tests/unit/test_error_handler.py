import pytest
from app.agent.error_handler import error_handler_node
from langchain_core.messages import AIMessage, ToolMessage


def make_state(messages):
    return {
        "execution_id": "execution-1",
        "messages": messages,
        "memory_summary": None,
        "iteration_count": 1,
        "execution_status": "running",
        "pending_approval": None,
        "pending_clarification": None,
    }


def test_error_handler_accepts_failed_tool_result():
    state = make_state([
        AIMessage(content="", tool_calls=[
            {
                "name": "create_task",
                "args": {"title": "Task A"},
                "id": "call-1",
                "type": "tool_call",
            }
        ]),
        ToolMessage(
            content="Task validation failed",
            tool_call_id="call-1",
            status="error",
        ),
    ])

    result = error_handler_node(state)

    assert result == {"execution_status": "running"}


def test_error_handler_preserves_partial_success():
    successful_result = ToolMessage(
        content="Task created",
        tool_call_id="call-1",
    )
    failed_result = ToolMessage(
        content="Task update failed",
        tool_call_id="call-2",
        status="error",
    )

    state = make_state([
        AIMessage(content=""),
        successful_result,
        failed_result,
    ])

    result = error_handler_node(state)

    assert result == {"execution_status": "running"}
    assert state["messages"][1] is successful_result
    assert state["messages"][2] is failed_result


def test_error_handler_rejects_state_without_failed_results():
    state = make_state([
        AIMessage(content=""),
        ToolMessage(
            content="Task created",
            tool_call_id="call-1",
        ),
    ])

    with pytest.raises(ValueError, match="no failed tool results"):
        error_handler_node(state)