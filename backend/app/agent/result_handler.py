"""Result validation and state transition handling for TaskFlow AI."""

from langchain_core.messages import ToolMessage

from app.agent.state import AgentState
from app.agent.validators import validate_agent_state


def result_handler_node(state: AgentState) -> dict:
    """Validate tool results and prepare the workflow for its next step."""

    validate_agent_state(state)

    if not state["messages"]:
        raise ValueError("Cannot handle tool results without conversation messages.")

    latest_ai_message = next(
        (
            message
            for message in reversed(state["messages"])
            if getattr(message, "tool_calls", None)
        ),
        None,
    )

    if latest_ai_message is None:
        raise ValueError("No AI message containing tool calls was found.")

    expected_ids = [
        tool_call["id"]
        for tool_call in latest_ai_message.tool_calls
    ]

    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("The AI message contains duplicate tool-call IDs.")

    ai_message_index = state["messages"].index(latest_ai_message)

    actual_messages = [
        message
        for message in state["messages"][ai_message_index + 1 :]
        if isinstance(message, ToolMessage)
    ]

    actual_ids = [message.tool_call_id for message in actual_messages]

    if actual_ids != expected_ids:
        raise ValueError(
            "Tool results do not match the original tool-call IDs and order. "
            f"Expected {expected_ids}, received {actual_ids}."
        )

    execution_status = (
        "waiting_for_approval"
        if state["pending_approval"] is not None
        else "running"
    )

    return {"execution_status": execution_status}