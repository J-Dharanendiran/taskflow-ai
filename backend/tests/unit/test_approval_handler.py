import app.agent.approval_handler as approval_handler
import pytest
from langchain_core.messages import AIMessage, ToolMessage

PENDING_APPROVAL = {
    "approval_id": "approval-1",
    "deletion_request_id": "deletion-1",
    "task_id": "task-1",
    "tool_call_id": "call-delete",
}


def make_state():
    return {
        "execution_id": "execution-1",
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "delete_task",
                        "args": {"task_id": "task-1"},
                        "id": "call-delete",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                id="tool-result:call-delete",
                name="delete_task",
                tool_call_id="call-delete",
                content="Deletion pending approval.",
            ),
        ],
        "memory_summary": None,
        "iteration_count": 1,
        "execution_status": "waiting_for_approval",
        "pending_approval": PENDING_APPROVAL.copy(),
        "pending_clarification": None,
    }


def test_approved_decision_preserves_pending_approval(monkeypatch):
    monkeypatch.setattr(
        approval_handler,
        "interrupt",
        lambda payload: {
            "approval_id": "approval-1",
            "approved": True,
        },
    )

    state = make_state()

    result = approval_handler.approval_handler_node(state)

    assert result == {"execution_status": "waiting_for_approval"}


def test_rejected_decision_clears_pending_approval(monkeypatch):
    monkeypatch.setattr(
        approval_handler,
        "interrupt",
        lambda payload: {
            "approval_id": "approval-1",
            "approved": False,
        },
    )

    state = make_state()

    result = approval_handler.approval_handler_node(state)

    assert result["pending_approval"] is None
    assert result["execution_status"] == "running"

    rejection = result["messages"][0]

    assert isinstance(rejection, ToolMessage)
    assert rejection.tool_call_id == "call-delete"
    assert rejection.id == "tool-result:call-delete"
    assert "not deleted" in rejection.content


def test_rejects_mismatched_approval_id(monkeypatch):
    monkeypatch.setattr(
        approval_handler,
        "interrupt",
        lambda payload: {
            "approval_id": "another-approval",
            "approved": True,
        },
    )

    with pytest.raises(ValueError, match="does not match"):
        approval_handler.approval_handler_node(make_state())


def test_rejects_non_boolean_decision(monkeypatch):
    monkeypatch.setattr(
        approval_handler,
        "interrupt",
        lambda payload: {
            "approval_id": "approval-1",
            "approved": "yes",
        },
    )

    with pytest.raises(ValueError, match="boolean"):
        approval_handler.approval_handler_node(make_state())


def test_rejects_missing_pending_approval(monkeypatch):
    state = make_state()
    state["pending_approval"] = None
    state["execution_status"] = "running"

    with pytest.raises(ValueError, match="requires a pending approval"):
        approval_handler.approval_handler_node(state)