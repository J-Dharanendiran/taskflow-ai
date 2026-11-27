import pytest
from app.agent.state import AgentState, create_initial_state
from app.agent.validators import (
    validate_agent_state,
    validate_pending_approval,
    validate_pending_clarification,
)
from langchain_core.messages import AIMessage, HumanMessage


def valid_state(**overrides) -> AgentState:
    state = {
        "execution_id": "exec-1",
        "messages": [HumanMessage(content="Create a task", id="msg-1")],
        "memory_summary": None,
        "iteration_count": 0,
        "execution_status": "running",
        "pending_approval": None,
        "pending_clarification": None,
    }
    state.update(overrides)
    return state


def test_valid_running_state_is_accepted():
    state = valid_state()
    assert validate_agent_state(state) is state


def test_state_accepts_native_langchain_messages():
    state = valid_state(
        messages=[
            HumanMessage(content="Create a task", id="msg-1"),
            AIMessage(content="What should the task be called?", id="msg-2"),
        ]
    )
    validate_agent_state(state)


def test_negative_iteration_count_is_rejected():
    with pytest.raises(ValueError):
        validate_agent_state(valid_state(iteration_count=-1))


def test_waiting_for_approval_requires_approval_context():
    with pytest.raises(ValueError, match="waiting_for_approval"):
        validate_agent_state(
            valid_state(execution_status="waiting_for_approval")
        )


def test_waiting_for_clarification_requires_clarification_context():
    with pytest.raises(ValueError, match="waiting_for_clarification"):
        validate_agent_state(
            valid_state(execution_status="waiting_for_clarification")
        )


def test_pending_interactions_are_mutually_exclusive():
    approval = {
        "approval_id": "approval-1",
        "deletion_request_id": "deletion-1",
        "task_id": "task-1",
        "tool_call_id": "call-1",
    }
    clarification = {
        "question": "Which task do you mean?",
        "reason": "ambiguous_reference",
        "original_message_id": "msg-1",
    }
    with pytest.raises(ValueError, match="cannot both be active"):
        validate_agent_state(
            valid_state(
                execution_status="waiting_for_approval",
                pending_approval=approval,
                pending_clarification=clarification,
            )
        )


def test_terminal_state_cannot_keep_pending_interaction():
    clarification = {
        "question": "Which task do you mean?",
        "reason": "ambiguous_reference",
        "original_message_id": "msg-1",
    }
    with pytest.raises(ValueError, match="cannot retain"):
        validate_agent_state(
            valid_state(
                execution_status="completed",
                pending_clarification=clarification,
            )
        )


def test_pending_approval_payload_is_validated():
    payload = {
        "approval_id": "approval-1",
        "deletion_request_id": "deletion-1",
        "task_id": "task-1",
        "tool_call_id": "call-1",
    }
    assert validate_pending_approval(payload) is payload


def test_pending_clarification_payload_is_validated():
    payload = {
        "question": "Which task do you mean?",
        "reason": "missing_information",
        "original_message_id": "msg-1",
    }
    assert validate_pending_clarification(payload) is payload


def test_invalid_clarification_reason_is_rejected():
    payload = {
        "question": "Which task?",
        "reason": "guess",
        "original_message_id": "msg-1",
    }
    with pytest.raises(ValueError):
        validate_pending_clarification(payload)



def test_initial_state_factory_sets_all_seven_fields():
    message = HumanMessage(content="Create a task", id="msg-1")
    state = create_initial_state(
        execution_id="exec-2",
        messages=[message],
        memory_summary="Older context",
    )

    assert set(state) == {
        "execution_id",
        "messages",
        "memory_summary",
        "iteration_count",
        "execution_status",
        "pending_approval",
        "pending_clarification",
    }
    assert state["execution_id"] == "exec-2"
    assert state["messages"] == [message]
    assert state["memory_summary"] == "Older context"
    assert state["iteration_count"] == 0
    assert state["execution_status"] == "running"
    assert state["pending_approval"] is None
    assert state["pending_clarification"] is None


def test_initial_state_factory_rejects_empty_execution_id():
    with pytest.raises(ValueError, match="execution_id"):
        create_initial_state(execution_id=" ", messages=[])
