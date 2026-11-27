
"""Unit tests for TaskFlow AI conditional routing."""

import pytest
from app.agent.routing import (
    route_after_agent,
    route_after_approval_handler,
    route_after_result_handler,
)
from app.agent.state import create_initial_state
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END


@pytest.fixture
def state():
    return create_initial_state(
        execution_id="execution-1",
        messages=[],
    )


def test_agent_routes_tool_calls_to_executor(state):
    state["messages"] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "list_tasks",
                    "args": {},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )
    ]

    assert route_after_agent(state) == "tool_executor"


@pytest.mark.parametrize(
    "status",
    ["completed", "failed", "waiting_for_clarification"],
)
def test_agent_routes_terminal_outcomes_to_end(state, status):
    state["execution_status"] = status

    assert route_after_agent(state) == END


def test_result_handler_routes_pending_approval(state):
    state["pending_approval"] = {
        "approval_id": "approval-1",
        "deletion_request_id": "request-1",
        "task_id": "task-1",
        "tool_call_id": "call-1",
    }

    assert route_after_result_handler(state) == "approval_handler"


def test_result_handler_routes_tool_errors(state):
    state["messages"] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "list_tasks",
                    "args": {},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content="Tool failed",
            tool_call_id="call-1",
            name="list_tasks",
            status="error",
        ),
    ]

    assert route_after_result_handler(state) == "error_handler"


def test_result_handler_routes_success_to_agent(state):
    state["messages"] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "list_tasks",
                    "args": {},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content="Tasks retrieved",
            tool_call_id="call-1",
            name="list_tasks",
        ),
    ]

    assert route_after_result_handler(state) == "agent"


def test_approval_handler_routes_approved_deletion(state):
    state["execution_status"] = "waiting_for_approval"
    state["pending_approval"] = {
        "approval_id": "approval-1",
        "deletion_request_id": "request-1",
        "task_id": "task-1",
        "tool_call_id": "call-1",
    }

    assert route_after_approval_handler(state) == "deletion_executor"


def test_approval_handler_routes_rejection_to_agent(state):
    state["execution_status"] = "running"
    state["pending_approval"] = None

    assert route_after_approval_handler(state) == "agent"


def test_approval_handler_rejects_invalid_state(state):
    state["execution_status"] = "completed"

    with pytest.raises(ValueError):
        route_after_approval_handler(state)
    