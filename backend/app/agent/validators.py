"""Targeted runtime validation for TaskFlow AI graph state."""

from typing import Literal

from langchain_core.messages import AnyMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.state import (
    AgentState,
    PendingApprovalState,
    PendingClarificationState,
)

ExecutionStatusValue = Literal[
    "running",
    "waiting_for_clarification",
    "waiting_for_approval",
    "completed",
    "failed",
]

ClarificationReasonValue = Literal[
    "missing_information",
    "ambiguous_reference",
    "unsupported_value",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class PendingApprovalModel(_StrictModel):
    approval_id: str = Field(min_length=1)
    deletion_request_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)


class PendingClarificationModel(_StrictModel):
    question: str = Field(min_length=1)
    reason: ClarificationReasonValue
    original_message_id: str = Field(min_length=1)


class AgentStateBoundaryModel(_StrictModel):
    """Validation model used only at critical state boundaries.

    The graph's declared schema remains the TypedDict in state.py.
    """

    execution_id: str = Field(min_length=1)
    messages: list[AnyMessage]
    memory_summary: str | None
    iteration_count: int = Field(ge=0)
    execution_status: ExecutionStatusValue
    pending_approval: PendingApprovalModel | None
    pending_clarification: PendingClarificationModel | None

    @model_validator(mode="after")
    def validate_interaction_invariants(self):
        approval = self.pending_approval
        clarification = self.pending_clarification

        if approval is not None and clarification is not None:
            raise ValueError(
                "pending_approval and pending_clarification cannot both be active."
            )

        if self.execution_status == "waiting_for_approval":
            if approval is None or clarification is not None:
                raise ValueError(
                    "waiting_for_approval requires pending_approval only."
                )

        if self.execution_status == "waiting_for_clarification":
            if clarification is None or approval is not None:
                raise ValueError(
                    "waiting_for_clarification requires pending_clarification only."
                )

        if self.execution_status in {"running", "completed", "failed"}:
            if approval is not None or clarification is not None:
                raise ValueError(
                    f"{self.execution_status} cannot retain an actionable pending interaction."
                )

        return self


def validate_agent_state(state: AgentState) -> AgentState:
    """Validate the complete state at a designated lifecycle boundary.

    Returns the original mapping so message objects and reducer semantics are
    not replaced by a Pydantic-generated copy.
    """
    AgentStateBoundaryModel.model_validate(state)
    return state


def validate_pending_approval(
    value: PendingApprovalState,
) -> PendingApprovalState:
    """Validate an approval interaction payload before adding it to state."""
    PendingApprovalModel.model_validate(value)
    return value


def validate_pending_clarification(
    value: PendingClarificationState,
) -> PendingClarificationState:
    """Validate a clarification payload before adding it to state."""
    PendingClarificationModel.model_validate(value)
    return value
