
"""Conditional routing functions for the TaskFlow AI graph."""

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END

from app.agent.state import AgentState


def _get_latest_tool_results(state: AgentState) -> list[ToolMessage]:
    """Return tool results associated with the latest AI tool-call message."""

    messages = state["messages"]

    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]

        if isinstance(message, AIMessage) and message.tool_calls:
            expected_ids = {
                tool_call["id"] for tool_call in message.tool_calls
            }

            return [
                item
                for item in messages[index + 1 :]
                if isinstance(item, ToolMessage)
                and item.tool_call_id in expected_ids
            ]

    return []


def route_after_agent(state: AgentState) -> str:
    """Route the Agent according to its execution outcome."""

    status = state["execution_status"]

    if status in {
        "completed",
        "failed",
        "waiting_for_clarification",
    }:
        return END

    if status == "running":
        if state["messages"]:
            latest_message = state["messages"][-1]

            if (
                isinstance(latest_message, AIMessage)
                and latest_message.tool_calls
            ):
                return "tool_executor"

    raise ValueError(
        f"Agent produced an unsupported routing state: {status}"
    )


def route_after_result_handler(state: AgentState) -> str:
    """Choose the next node after validating tool results."""

    if state["pending_approval"] is not None:
        return "approval_handler"

    tool_results = _get_latest_tool_results(state)

    if any(message.status == "error" for message in tool_results):
        return "error_handler"

    return "agent"


def route_after_approval_handler(state: AgentState) -> str:
    """Route an approved deletion or a rejected approval."""

    if (
        state["pending_approval"] is not None
        and state["execution_status"] == "waiting_for_approval"
    ):
        return "deletion_executor"

    if (
        state["pending_approval"] is None
        and state["execution_status"] == "running"
    ):
        return "agent"

    raise ValueError(
        "Approval Handler produced an unsupported routing state."
    )
    