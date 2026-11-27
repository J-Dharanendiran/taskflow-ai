"""Tool execution error handling for TaskFlow AI."""

from langchain_core.messages import ToolMessage

from app.agent.state import AgentState
from app.agent.validators import validate_agent_state


def error_handler_node(state: AgentState) -> dict:
    """Validate failed tool results and return control to the agent."""

    validate_agent_state(state)

    failed_messages = [
        message
        for message in state["messages"]
        if isinstance(message, ToolMessage) and message.status == "error"
    ]

    if not failed_messages:
        raise ValueError("Error Handler received no failed tool results.")

    return {"execution_status": "running"}