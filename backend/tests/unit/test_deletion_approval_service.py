import pytest
import pytest_asyncio
from app.database.base import Base
from app.models import DeletionApproval, DeletionExecution, DeletionRequest, Task
from app.services.deletion_approval_service import DeletionApprovalService
from app.services.exceptions import (
    ApprovalConflictError,
    ApprovalNotFoundError,
    InvalidApprovalStateError,
)
from app.services.task_service import TaskService
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    yield factory
    await engine.dispose()


async def create_task(session_factory, title="Remove this task"):
    async with session_factory() as session:
        return await TaskService(session).create_task(title=title)


async def create_request(session_factory, task_id, thread_id="thread-1"):
    async with session_factory() as session:
        return await DeletionApprovalService(session).create_request(
            task_id=task_id,
            thread_id=thread_id,
            execution_id="execution-1",
            tool_call_id="tool-call-1",
        )


@pytest.mark.asyncio
async def test_create_request_persists_request_and_approval_without_deleting_task(
    session_factory,
):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        stored_request = await session.get(DeletionRequest, created.deletion_request.id)
        stored_approval = await session.get(DeletionApproval, created.approval.id)
        stored_task = await session.get(Task, task.id)

    assert stored_request.status == "PENDING"
    assert stored_request.task_title_snapshot == "Remove this task"
    assert stored_request.thread_id == "thread-1"
    assert stored_approval.decision == "PENDING"
    assert stored_approval.deletion_request_id == stored_request.id
    assert stored_task is not None


@pytest.mark.asyncio
async def test_replaying_same_delete_tool_call_returns_same_durable_request(
    session_factory,
):
    task = await create_task(session_factory)
    first = await create_request(session_factory, task.id)
    second = await create_request(session_factory, task.id)

    assert second.deletion_request.id == first.deletion_request.id
    assert second.approval.id == first.approval.id


@pytest.mark.asyncio
async def test_approval_rejection_is_persisted_and_idempotent(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        first = await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=False
        )
        repeated = await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=False
        )

    assert first.status == "REJECTED"
    assert repeated.status == "REJECTED"

    async with session_factory() as session:
        approval = await session.get(DeletionApproval, created.approval.id)
    assert approval.decision == "REJECTED"


@pytest.mark.asyncio
async def test_conflicting_second_decision_is_rejected(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=True
        )
        with pytest.raises(ApprovalConflictError):
            await service.decide(
                thread_id="thread-1", approval_id=created.approval.id, approved=False
            )


@pytest.mark.asyncio
async def test_approval_cannot_be_used_from_another_thread(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        with pytest.raises(ApprovalNotFoundError):
            await DeletionApprovalService(session).decide(
                thread_id="different-thread",
                approval_id=created.approval.id,
                approved=True,
            )


@pytest.mark.asyncio
async def test_deletion_cannot_execute_before_explicit_approval(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        with pytest.raises(InvalidApprovalStateError):
            await DeletionApprovalService(session).execute_approved_deletion(
                thread_id="thread-1", approval_id=created.approval.id
            )


@pytest.mark.asyncio
async def test_approved_deletion_and_execution_ledger_commit_together(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=True
        )
        result = await service.execute_approved_deletion(
            thread_id="thread-1", approval_id=created.approval.id
        )

    assert result.status == "COMPLETED"
    assert result.already_executed is False

    async with session_factory() as session:
        assert await session.get(Task, task.id) is None
        request = await session.get(DeletionRequest, created.deletion_request.id)
        executions = list((await session.scalars(select(DeletionExecution))).all())

    assert request.status == "COMPLETED"
    assert len(executions) == 1
    assert executions[0].deletion_request_id == created.deletion_request.id


@pytest.mark.asyncio
async def test_replaying_completed_deletion_returns_ledger_without_second_delete(
    session_factory,
):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=True
        )
        first = await service.execute_approved_deletion(
            thread_id="thread-1", approval_id=created.approval.id
        )
        replay = await service.execute_approved_deletion(
            thread_id="thread-1", approval_id=created.approval.id
        )

    assert first.status == "COMPLETED"
    assert replay.status == "COMPLETED"
    assert replay.already_executed is True

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(DeletionExecution)
        )
    assert count == 1


@pytest.mark.asyncio
async def test_missing_task_is_reconciled_as_cancelled_not_completed(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=True
        )
        await TaskService(session).delete_task(task.id)
        result = await service.execute_approved_deletion(
            thread_id="thread-1", approval_id=created.approval.id
        )

    assert result.status == "CANCELLED"
    assert result.already_executed is False

    async with session_factory() as session:
        request = await session.get(DeletionRequest, created.deletion_request.id)
        execution = await session.scalar(select(DeletionExecution))
        ledger_count = await session.scalar(
            select(func.count()).select_from(DeletionExecution)
        )

    assert request.status == "CANCELLED"
    assert request.cancellation_reason == "fulfilled_elsewhere"
    assert ledger_count == 1
    assert execution.status == "CANCELLED"


@pytest.mark.asyncio
async def test_rejection_never_deletes_the_task(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=False
        )
        with pytest.raises(InvalidApprovalStateError):
            await service.execute_approved_deletion(
                thread_id="thread-1", approval_id=created.approval.id
            )
        stored_task = await session.get(Task, task.id)

    assert stored_task is not None


@pytest.mark.asyncio
async def test_same_tool_call_cannot_be_reused_for_a_different_task(session_factory):
    first_task = await create_task(session_factory, title="First task")
    second_task = await create_task(session_factory, title="Second task")
    await create_request(session_factory, first_task.id)

    async with session_factory() as session:
        with pytest.raises(ApprovalConflictError):
            await DeletionApprovalService(session).create_request(
                task_id=second_task.id,
                thread_id="thread-1",
                execution_id="execution-1",
                tool_call_id="tool-call-1",
            )


@pytest.mark.asyncio
async def test_invalid_approval_value_is_rejected(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        with pytest.raises(ValueError, match="explicit boolean"):
            await DeletionApprovalService(session).decide(
                thread_id="thread-1",
                approval_id=created.approval.id,
                approved="yes",
            )


@pytest.mark.asyncio
async def test_failed_delete_rolls_back_and_in_progress_claim_can_resume(
    session_factory, monkeypatch
):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=True
        )
        original_delete = service.tasks.delete_task

        async def delete_then_fail(task_id, *, commit=True):
            await original_delete(task_id, commit=False)
            raise RuntimeError("simulated failure before transaction commit")

        monkeypatch.setattr(service.tasks, "delete_task", delete_then_fail)
        with pytest.raises(RuntimeError, match="simulated failure"):
            await service.execute_approved_deletion(
                thread_id="thread-1", approval_id=created.approval.id
            )

        monkeypatch.setattr(service.tasks, "delete_task", original_delete)
        resumed = await service.execute_approved_deletion(
            thread_id="thread-1", approval_id=created.approval.id
        )

    assert resumed.status == "COMPLETED"
    assert resumed.already_executed is False

    async with session_factory() as session:
        stored_task = await session.get(Task, task.id)
        stored_request = await session.get(DeletionRequest, created.deletion_request.id)
        execution = await session.scalar(select(DeletionExecution))

    assert stored_task is None
    assert stored_request.status == "COMPLETED"
    assert execution.status == "COMPLETED"


@pytest.mark.asyncio
async def test_commit_response_loss_is_reconciled_from_execution_ledger(
    session_factory, monkeypatch
):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=True
        )
        original_commit = session.commit
        commit_calls = 0

        async def commit_then_lose_response():
            nonlocal commit_calls
            commit_calls += 1
            await original_commit()
            if commit_calls == 2:
                raise ConnectionError("simulated lost commit response")

        monkeypatch.setattr(session, "commit", commit_then_lose_response)
        result = await service.execute_approved_deletion(
            thread_id="thread-1", approval_id=created.approval.id
        )

    assert result.status == "COMPLETED"
    assert result.already_executed is True

    async with session_factory() as session:
        assert await session.get(Task, task.id) is None
        execution_count = await session.scalar(
            select(func.count()).select_from(DeletionExecution)
        )
    assert execution_count == 1


@pytest.mark.asyncio
async def test_approval_and_request_correlation_must_match(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        request = await session.get(DeletionRequest, created.deletion_request.id)
        request.execution_id = "different-execution"
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(InvalidApprovalStateError, match="correlation"):
            await DeletionApprovalService(session).decide(
                thread_id="thread-1",
                approval_id=created.approval.id,
                approved=True,
            )


@pytest.mark.asyncio
async def test_terminal_execution_failure_is_recorded_in_request_and_ledger(
    session_factory,
):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=True
        )
        request = await session.get(DeletionRequest, created.deletion_request.id)
        await service._claim_execution(request=request)
        failed = await service.mark_execution_failed(
            thread_id="thread-1",
            approval_id=created.approval.id,
            failure_code="PERMANENT_TOOL_FAILURE",
            failure_message="The delete operation cannot be completed.",
        )

    async with session_factory() as session:
        execution = await session.scalar(select(DeletionExecution))
        stored_task = await session.get(Task, task.id)

    assert failed.status == "FAILED"
    assert execution.status == "FAILED"
    assert execution.failure_code == "PERMANENT_TOOL_FAILURE"
    assert stored_task is not None


@pytest.mark.asyncio
async def test_in_progress_execution_is_not_reported_as_completed(session_factory):
    task = await create_task(session_factory)
    created = await create_request(session_factory, task.id)

    async with session_factory() as session:
        service = DeletionApprovalService(session)
        await service.decide(
            thread_id="thread-1", approval_id=created.approval.id, approved=True
        )
        request = await session.get(DeletionRequest, created.deletion_request.id)
        execution = await service._claim_execution(request=request)

    assert execution.status == "IN_PROGRESS"
    assert execution.completed_at is None

    async with session_factory() as session:
        result = await DeletionApprovalService(session).execute_approved_deletion(
            thread_id="thread-1", approval_id=created.approval.id
        )

    assert result.status == "COMPLETED"
