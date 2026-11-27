
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.agent.deletion_executor as deletion_executor
import pytest
from app.services.exceptions import (
    InvalidApprovalStateError,
    UncertainExecutionOutcomeError,
)
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


class FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def install_service_mock(monkeypatch, service):
    monkeypatch.setattr(
        deletion_executor,
        "AsyncSessionLocal",
        FakeSessionContext,
    )
    monkeypatch.setattr(
        deletion_executor,
        "DeletionApprovalService",
        lambda session: service,
    )


def completed_result(already_executed=False):
    return SimpleNamespace(
        status="completed",
        task_id="task-1",
        already_executed=already_executed,
    )


def cancelled_result():
    return SimpleNamespace(
        status="cancelled",
        task_id="task-1",
        already_executed=False,
    )


def make_service(execution_side_effect=None, execution_result=None):
    return SimpleNamespace(
        execute_approved_deletion=AsyncMock(
            side_effect=execution_side_effect,
            return_value=execution_result,
        ),
        mark_execution_failed=AsyncMock(),
    )


async def execute_node():
    return await deletion_executor.deletion_executor_node(
        make_state(),
        {"configurable": {"thread_id": "thread-1"}},
    )


@pytest.mark.asyncio
async def test_executes_approved_deletion(monkeypatch):
    service = make_service(execution_result=completed_result())
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    service.execute_approved_deletion.assert_awaited_once_with(
        thread_id="thread-1",
        approval_id="approval-1",
    )
    service.mark_execution_failed.assert_not_awaited()

    message = result["messages"][0]

    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-delete"
    assert message.id == "tool-result:call-delete"
    assert "successfully deleted" in message.content
    assert message.status != "error"
    assert result["pending_approval"] is None
    assert result["execution_status"] == "running"


@pytest.mark.asyncio
async def test_does_not_repeat_already_completed_deletion(monkeypatch):
    service = make_service(
        execution_result=completed_result(already_executed=True)
    )
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    assert "already been completed" in result["messages"][0].content
    assert result["messages"][0].status != "error"
    service.execute_approved_deletion.assert_awaited_once()
    service.mark_execution_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_handles_task_already_removed(monkeypatch):
    service = make_service(execution_result=cancelled_result())
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    message = result["messages"][0]

    assert "no longer exists" in message.content
    assert "did not delete" in message.content
    assert message.status != "error"
    service.mark_execution_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_retries_transient_failure_then_succeeds(monkeypatch):
    service = make_service(
        execution_side_effect=[
            ConnectionError("Temporary database connection failure"),
            completed_result(),
        ]
    )
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    assert service.execute_approved_deletion.await_count == 2
    service.mark_execution_failed.assert_not_awaited()

    message = result["messages"][0]

    assert message.status != "error"
    assert "successfully deleted" in message.content


@pytest.mark.asyncio
async def test_succeeds_after_using_both_transient_retries(monkeypatch):
    service = make_service(
        execution_side_effect=[
            ConnectionError("Temporary failure 1"),
            TimeoutError("Temporary failure 2"),
            completed_result(),
        ]
    )
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    assert service.execute_approved_deletion.await_count == 3
    service.mark_execution_failed.assert_not_awaited()

    message = result["messages"][0]

    assert message.status != "error"
    assert "successfully deleted" in message.content


@pytest.mark.asyncio
async def test_persists_failure_after_transient_retries_are_exhausted(
    monkeypatch,
):
    service = make_service(
        execution_side_effect=ConnectionError("Database remains unavailable")
    )
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    assert service.execute_approved_deletion.await_count == 3

    service.mark_execution_failed.assert_awaited_once_with(
        thread_id="thread-1",
        approval_id="approval-1",
        failure_code="TRANSIENT_RETRIES_EXHAUSTED",
        failure_message="Database remains unavailable",
    )

    message = result["messages"][0]

    assert message.status == "error"
    assert "recorded as FAILED" in message.content
    assert "Database remains unavailable" in message.content


@pytest.mark.asyncio
async def test_persists_permanent_execution_failure(monkeypatch):
    service = make_service(
        execution_side_effect=RuntimeError("Permanent database constraint error")
    )
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    service.execute_approved_deletion.assert_awaited_once()

    service.mark_execution_failed.assert_awaited_once_with(
        thread_id="thread-1",
        approval_id="approval-1",
        failure_code="PERMANENT_DELETION_FAILURE",
        failure_message="Permanent database constraint error",
    )

    message = result["messages"][0]

    assert message.status == "error"
    assert "recorded as FAILED" in message.content
    assert "Permanent database constraint error" in message.content


@pytest.mark.asyncio
async def test_uncertain_outcome_is_not_retried_or_marked_failed(monkeypatch):
    service = make_service(
        execution_side_effect=UncertainExecutionOutcomeError(
            "Commit outcome uncertain"
        )
    )
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    service.execute_approved_deletion.assert_awaited_once()
    service.mark_execution_failed.assert_not_awaited()

    message = result["messages"][0]

    assert message.status == "error"
    assert "outcome is uncertain" in message.content
    assert "Do not assume" in message.content


@pytest.mark.asyncio
async def test_does_not_claim_failure_when_no_execution_claim_exists(
    monkeypatch,
):
    service = make_service(
        execution_side_effect=RuntimeError("Approval context unavailable")
    )
    service.mark_execution_failed.side_effect = InvalidApprovalStateError(
        "A claimed in-progress execution is required to record failure."
    )
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    service.execute_approved_deletion.assert_awaited_once()
    service.mark_execution_failed.assert_awaited_once()

    message = result["messages"][0]

    assert message.status == "error"
    assert "could not be confirmed" in message.content
    assert "Approval context unavailable" in message.content
    assert "recorded as FAILED" not in message.content


@pytest.mark.asyncio
async def test_reports_failure_when_failure_persistence_fails(monkeypatch):
    service = make_service(
        execution_side_effect=RuntimeError("Permanent execution failure")
    )
    service.mark_execution_failed.side_effect = ConnectionError(
        "Failure ledger unavailable"
    )
    install_service_mock(monkeypatch, service)

    result = await execute_node()

    service.execute_approved_deletion.assert_awaited_once()
    service.mark_execution_failed.assert_awaited_once()

    message = result["messages"][0]

    assert message.status == "error"
    assert "could not be confirmed" in message.content
    assert "Permanent execution failure" in message.content
    assert "Failure ledger unavailable" in message.content
    assert "recorded as FAILED" not in message.content


@pytest.mark.asyncio
async def test_rejects_missing_pending_approval():
    state = make_state()
    state["pending_approval"] = None
    state["execution_status"] = "running"

    with pytest.raises(ValueError, match="requires a pending approval"):
        await deletion_executor.deletion_executor_node(
            state,
            {"configurable": {"thread_id": "thread-1"}},
        )
