"""LangGraph runtime state contract for TaskFlow AI.

The seven top-level fields are frozen by
``docs/phase_5_state_contract.md``. Durable application records remain in SQLite.
"""

from collections.abc import Sequence
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

ExecutionStatus = Literal[
    "running",
    "waiting_for_clarification",
    "waiting_for_approval",
    "completed",
    "failed",
]

ClarificationReason = Literal[
    "missing_information",
    "ambiguous_reference",
    "unsupported_value",
]


class PendingApprovalState(TypedDict):
    """Runtime reference to a durable deletion approval record."""

    approval_id: str
    deletion_request_id: str
    task_id: str
    tool_call_id: str


class PendingClarificationState(TypedDict):
    """Runtime context for a clarification that ended the prior invocation."""

    question: str
    reason: ClarificationReason
    original_message_id: str


class AgentState(TypedDict):
    """Execution-focused state for the unified TaskFlow AI graph.

    ``thread_id`` belongs in LangGraph config, not this state.
    Conversation history, approvals, and execution outcomes remain durable
    application records in SQLite.
    """

    execution_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    memory_summary: str | None
    iteration_count: int
    execution_status: ExecutionStatus
    pending_approval: PendingApprovalState | None
    pending_clarification: PendingClarificationState | None



def create_initial_state(
    *,
    execution_id: str,
    messages: Sequence[AnyMessage],
    memory_summary: str | None = None,
) -> AgentState:
    """Build the seven-field state for a new logical execution.

    The caller is responsible for loading bounded history, inserting the
    incoming user message idempotently in SQLite, and supplying the execution
    identifier. This helper performs no persistence and creates no IDs.
    """
    if not execution_id.strip():
        raise ValueError("execution_id must be non-empty.")

    state: AgentState = {
        "execution_id": execution_id,
        "messages": list(messages),
        "memory_summary": memory_summary,
        "iteration_count": 0,
        "execution_status": "running",
        "pending_approval": None,
        "pending_clarification": None,
    }
    return state
