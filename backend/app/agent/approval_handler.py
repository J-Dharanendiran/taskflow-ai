"""Human approval interrupt handling for TaskFlow AI."""

from langchain_core.messages import ToolMessage
from langgraph.types import interrupt

from app.agent.state import AgentState
from app.agent.validators import validate_agent_state


def approval_handler_node(state: AgentState) -> dict:
    """Interrupt for human approval and process the resumed decision."""

    validate_agent_state(state)

    pending = state["pending_approval"]

    if pending is None:
        raise ValueError("Approval Handler requires a pending approval.")

    if state["execution_status"] != "waiting_for_approval":
        raise ValueError(
            "Approval Handler requires waiting_for_approval status."
        )

    decision = interrupt(
        {
            "type": "deletion_approval",
            "approval_id": pending["approval_id"],
            "deletion_request_id": pending["deletion_request_id"],
            "task_id": pending["task_id"],
            "message": "Human approval is required before deleting this task.",
        }
    )

    if not isinstance(decision, dict):
        raise ValueError("Approval decision must be a dictionary.")

    if decision.get("approval_id") != pending["approval_id"]:
        raise ValueError("Approval decision does not match the pending approval.")

    approved = decision.get("approved")

    if type(approved) is not bool:
        raise ValueError("Approval decision must contain a boolean 'approved' value.")

    if approved:
        # Keep the pending approval intact.
        # The graph router will send this state to Deletion Executor.
        return {"execution_status": "waiting_for_approval"}

    # Rejection completes the original delete tool call.
    # The stable message ID replaces its earlier pending-approval result.
    rejection_result = ToolMessage(
        id=f"tool-result:{pending['tool_call_id']}",
        name="delete_task",
        tool_call_id=pending["tool_call_id"],
        content="Deletion was rejected. The task was not deleted.",
    )

    return {
        "messages": [rejection_result],
        "pending_approval": None,
        "execution_status": "running",
    }