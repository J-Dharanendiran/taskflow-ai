"""Application-owned deletion approval and idempotent execution lifecycle."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DeletionApproval, DeletionExecution, DeletionRequest, Task
from app.services.exceptions import (
    ApprovalConflictError,
    ApprovalNotFoundError,
    InvalidApprovalStateError,
    UncertainExecutionOutcomeError,
)
from app.services.task_service import TaskService


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class DeletionRequestCreated:
    deletion_request: DeletionRequest
    approval: DeletionApproval


@dataclass(frozen=True)
class DeletionExecutionResult:
    deletion_request_id: str
    approval_id: str
    task_id: str
    status: str
    already_executed: bool = False


class DeletionApprovalService:
    """Owns the durable lifecycle; graph state/checkpoints are not authoritative."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.tasks = TaskService(session)

    async def _load_approval_context(
        self,
        *,
        thread_id: str,
        approval_id: str,
    ) -> tuple[DeletionApproval, DeletionRequest]:
        approval = await self.session.get(DeletionApproval, approval_id)
        if approval is None:
            raise ApprovalNotFoundError("Approval was not found for this conversation.")
        await self.session.refresh(approval)
        if approval.thread_id != thread_id:
            raise ApprovalNotFoundError("Approval was not found for this conversation.")

        request = await self.session.get(DeletionRequest, approval.deletion_request_id)
        if request is None:
            raise ApprovalNotFoundError(
                "The deletion request associated with this approval was not found."
            )
        await self.session.refresh(request)

        if (
            request.thread_id != approval.thread_id
            or request.execution_id != approval.execution_id
            or request.tool_call_id != approval.tool_call_id
        ):
            raise InvalidApprovalStateError(
                "The approval and deletion request correlation data do not match."
            )

        return approval, request

    async def _find_request_for_tool_call(
        self,
        *,
        thread_id: str,
        execution_id: str,
        tool_call_id: str,
    ) -> DeletionRequest | None:
        return await self.session.scalar(
            select(DeletionRequest).where(
                DeletionRequest.thread_id == thread_id,
                DeletionRequest.execution_id == execution_id,
                DeletionRequest.tool_call_id == tool_call_id,
            )
        )

    async def _get_created_request(
        self,
        *,
        task_id: str,
        thread_id: str,
        execution_id: str,
        tool_call_id: str,
    ) -> DeletionRequestCreated | None:
        existing_request = await self._find_request_for_tool_call(
            thread_id=thread_id,
            execution_id=execution_id,
            tool_call_id=tool_call_id,
        )
        if existing_request is None:
            return None
        if existing_request.task_id != task_id:
            raise ApprovalConflictError(
                "The originating tool call is already associated with another task."
            )

        existing_approval = await self.session.scalar(
            select(DeletionApproval).where(
                DeletionApproval.deletion_request_id == existing_request.id
            )
        )
        if existing_approval is None:
            raise InvalidApprovalStateError(
                "A persisted deletion request has no associated approval record."
            )
        if (
            existing_approval.thread_id != existing_request.thread_id
            or existing_approval.execution_id != existing_request.execution_id
            or existing_approval.tool_call_id != existing_request.tool_call_id
        ):
            raise InvalidApprovalStateError(
                "The approval and deletion request correlation data do not match."
            )
        return DeletionRequestCreated(existing_request, existing_approval)

    async def create_request(
        self,
        *,
        task_id: str,
        thread_id: str,
        execution_id: str,
        tool_call_id: str,
    ) -> DeletionRequestCreated:
        for name, value in (
            ("task_id", task_id),
            ("thread_id", thread_id),
            ("execution_id", execution_id),
            ("tool_call_id", tool_call_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")

        existing = await self._get_created_request(
            task_id=task_id,
            thread_id=thread_id,
            execution_id=execution_id,
            tool_call_id=tool_call_id,
        )
        if existing is not None:
            return existing

        task = await self.tasks.get_task(task_id)
        request = DeletionRequest(
            task_id=task.id,
            task_title_snapshot=task.title,
            thread_id=thread_id,
            execution_id=execution_id,
            tool_call_id=tool_call_id,
            status="PENDING",
        )
        approval = DeletionApproval(
            deletion_request=request,
            thread_id=thread_id,
            execution_id=execution_id,
            tool_call_id=tool_call_id,
            decision="PENDING",
        )
        self.session.add_all([request, approval])
        try:
            await self.session.commit()
        except IntegrityError:
            # Another invocation may have inserted this idempotency key after
            # our initial read. Reconcile instead of creating a second request.
            await self.session.rollback()
            existing = await self._get_created_request(
                task_id=task_id,
                thread_id=thread_id,
                execution_id=execution_id,
                tool_call_id=tool_call_id,
            )
            if existing is not None:
                return existing
            raise

        await self.session.refresh(request)
        await self.session.refresh(approval)
        return DeletionRequestCreated(request, approval)

    async def decide(
        self,
        *,
        thread_id: str,
        approval_id: str,
        approved: bool,
    ) -> DeletionRequest:
        if not isinstance(approved, bool):
            raise ValueError("Approval decision must be an explicit boolean.")

        approval, request = await self._load_approval_context(
            thread_id=thread_id,
            approval_id=approval_id,
        )
        requested_decision = "APPROVED" if approved else "REJECTED"

        if approval.decision != "PENDING":
            if approval.decision == requested_decision:
                return request
            raise ApprovalConflictError("This approval has already been resolved differently.")

        if request.status != "PENDING":
            raise InvalidApprovalStateError(
                f"Deletion request cannot be decided from status {request.status}."
            )

        now = utc_now()
        approval_update = await self.session.execute(
            update(DeletionApproval)
            .where(
                DeletionApproval.id == approval_id,
                DeletionApproval.thread_id == thread_id,
                DeletionApproval.decision == "PENDING",
            )
            .values(decision=requested_decision, decided_at=now)
            .execution_options(synchronize_session=False)
        )
        if approval_update.rowcount != 1:
            await self.session.rollback()
            return await self._reconcile_decision(
                thread_id=thread_id,
                approval_id=approval_id,
                requested_decision=requested_decision,
            )

        request_update = await self.session.execute(
            update(DeletionRequest)
            .where(
                DeletionRequest.id == request.id,
                DeletionRequest.thread_id == thread_id,
                DeletionRequest.status == "PENDING",
            )
            .values(status=requested_decision, decided_at=now)
            .execution_options(synchronize_session=False)
        )
        if request_update.rowcount != 1:
            await self.session.rollback()
            raise InvalidApprovalStateError(
                "The deletion request changed while its approval was being recorded."
            )

        try:
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            return await self._reconcile_decision(
                thread_id=thread_id,
                approval_id=approval_id,
                requested_decision=requested_decision,
                original_error=exc,
            )

        await self.session.refresh(approval)
        await self.session.refresh(request)
        return request

    async def _reconcile_decision(
        self,
        *,
        thread_id: str,
        approval_id: str,
        requested_decision: str,
        original_error: Exception | None = None,
    ) -> DeletionRequest:
        try:
            approval, request = await self._load_approval_context(
                thread_id=thread_id,
                approval_id=approval_id,
            )
        except Exception as exc:
            raise UncertainExecutionOutcomeError(
                "The approval decision could not be reconciled with the database."
            ) from exc

        if approval.decision == requested_decision:
            allowed_request_statuses = (
                {"REJECTED"}
                if requested_decision == "REJECTED"
                else {"APPROVED", "COMPLETED", "FAILED", "CANCELLED"}
            )
            if request.status not in allowed_request_statuses:
                raise InvalidApprovalStateError(
                    "The approval decision and deletion request status are inconsistent."
                )
            return request
        if approval.decision != "PENDING":
            raise ApprovalConflictError("This approval has already been resolved differently.")
        if original_error is not None:
            raise original_error
        raise InvalidApprovalStateError(
            "The approval decision was not committed; retry the same decision."
        )

    async def mark_execution_failed(
        self,
        *,
        thread_id: str,
        approval_id: str,
        failure_code: str,
        failure_message: str,
    ) -> DeletionRequest:
        """Persist a terminal deletion failure after retry policy is exhausted."""
        approval, request = await self._load_approval_context(
            thread_id=thread_id,
            approval_id=approval_id,
        )
        if request.status == "FAILED":
            return request
        if request.status == "COMPLETED":
            raise InvalidApprovalStateError(
                "A completed deletion cannot be changed to failed."
            )
        if approval.decision != "APPROVED" or request.status != "APPROVED":
            raise InvalidApprovalStateError(
                f"Deletion request cannot fail from status {request.status}."
            )
        if not isinstance(failure_code, str) or not failure_code.strip():
            raise ValueError("failure_code must be a non-empty string.")
        if not isinstance(failure_message, str):
            raise ValueError("failure_message must be a string.")

        execution = await self.session.scalar(
            select(DeletionExecution).where(
                DeletionExecution.deletion_request_id == request.id
            )
        )
        if execution is None or execution.status != "IN_PROGRESS":
            raise InvalidApprovalStateError(
                "A claimed in-progress execution is required to record failure."
            )

        request.status = "FAILED"
        request.failure_code = failure_code[:80]
        request.failure_message = failure_message
        execution.status = "FAILED"
        execution.failure_code = failure_code[:80]
        execution.failure_message = failure_message
        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def _claim_execution(
        self,
        *,
        request: DeletionRequest,
    ) -> DeletionExecution:
        """Create the durable IN_PROGRESS claim before attempting task deletion."""
        execution = DeletionExecution(
            deletion_request_id=request.id,
            task_id=request.task_id,
            status="IN_PROGRESS",
            started_at=utc_now(),
        )
        self.session.add(execution)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.session.scalar(
                select(DeletionExecution).where(
                    DeletionExecution.deletion_request_id == request.id
                )
            )
            if existing is not None:
                return existing
            raise
        except Exception as exc:
            await self.session.rollback()
            try:
                existing = await self.session.scalar(
                    select(DeletionExecution).where(
                        DeletionExecution.deletion_request_id == request.id
                    )
                )
            except Exception:
                raise UncertainExecutionOutcomeError(
                    "The deletion execution claim could not be reconciled."
                ) from exc
            if existing is not None:
                return existing
            raise

        await self.session.refresh(execution)
        return execution

    async def _reconcile_execution_after_commit_error(
        self,
        *,
        request_id: str,
        approval_id: str,
        task_id: str,
        original_error: Exception,
    ) -> DeletionExecutionResult:
        """Use the ledger and task row to decide whether retry is safe."""
        try:
            execution = await self.session.scalar(
                select(DeletionExecution).where(
                    DeletionExecution.deletion_request_id == request_id
                )
            )
            request = await self.session.get(DeletionRequest, request_id)
            if execution is None or request is None:
                raise UncertainExecutionOutcomeError(
                    "The deletion request or execution claim is missing during reconciliation."
                ) from original_error

            if execution.status == "COMPLETED":
                if request.status != "COMPLETED":
                    request.status = "COMPLETED"
                    request.completed_at = execution.completed_at
                    await self.session.commit()
                return DeletionExecutionResult(
                    deletion_request_id=request_id,
                    approval_id=approval_id,
                    task_id=task_id,
                    status="COMPLETED",
                    already_executed=True,
                )

            if execution.status == "CANCELLED":
                if request.status != "CANCELLED":
                    request.status = "CANCELLED"
                    request.cancellation_reason = "fulfilled_elsewhere"
                    await self.session.commit()
                return DeletionExecutionResult(
                    deletion_request_id=request_id,
                    approval_id=approval_id,
                    task_id=task_id,
                    status="CANCELLED",
                )

            if execution.status == "FAILED":
                raise InvalidApprovalStateError(
                    "The deletion execution has already failed permanently."
                ) from original_error

            task = await self.session.get(Task, task_id)
            if task is not None and execution.status == "IN_PROGRESS":
                # The atomic delete/complete transaction did not commit. The
                # durable claim remains, and retrying this same request is safe.
                raise original_error

            if task is None and execution.status == "IN_PROGRESS":
                request.status = "CANCELLED"
                request.cancellation_reason = "fulfilled_elsewhere"
                execution.status = "CANCELLED"
                await self.session.commit()
                return DeletionExecutionResult(
                    deletion_request_id=request_id,
                    approval_id=approval_id,
                    task_id=task_id,
                    status="CANCELLED",
                )

            raise InvalidApprovalStateError(
                f"Unsupported execution state during recovery: {execution.status}."
            ) from original_error
        except (UncertainExecutionOutcomeError, InvalidApprovalStateError):
            raise
        except Exception as reconciliation_error:
            await self.session.rollback()
            if reconciliation_error is original_error:
                raise
            raise UncertainExecutionOutcomeError(
                "The deletion outcome could not be determined from the execution ledger."
            ) from original_error

    async def execute_approved_deletion(
        self,
        *,
        thread_id: str,
        approval_id: str,
    ) -> DeletionExecutionResult:
        approval, request = await self._load_approval_context(
            thread_id=thread_id,
            approval_id=approval_id,
        )
        if approval.decision != "APPROVED":
            raise InvalidApprovalStateError("Deletion cannot execute without recorded approval.")

        execution = await self.session.scalar(
            select(DeletionExecution).where(
                DeletionExecution.deletion_request_id == request.id
            )
        )
        if execution is not None:
            if execution.status == "COMPLETED":
                if request.status != "COMPLETED":
                    request.status = "COMPLETED"
                    request.completed_at = execution.completed_at
                    await self.session.commit()
                return DeletionExecutionResult(
                    deletion_request_id=request.id,
                    approval_id=approval.id,
                    task_id=request.task_id,
                    status="COMPLETED",
                    already_executed=True,
                )
            if execution.status == "CANCELLED":
                if request.status != "CANCELLED":
                    request.status = "CANCELLED"
                    request.cancellation_reason = "fulfilled_elsewhere"
                    await self.session.commit()
                return DeletionExecutionResult(
                    deletion_request_id=request.id,
                    approval_id=approval.id,
                    task_id=request.task_id,
                    status="CANCELLED",
                )
            if execution.status == "FAILED":
                if request.status != "FAILED":
                    request.status = "FAILED"
                    request.failure_code = execution.failure_code
                    request.failure_message = execution.failure_message
                    await self.session.commit()
                raise InvalidApprovalStateError(
                    "The deletion execution has already failed permanently."
                )
            if request.status != "APPROVED":
                raise InvalidApprovalStateError(
                    "An in-progress execution requires an approved request."
                )
        elif request.status != "APPROVED":
            raise InvalidApprovalStateError(
                "A deletion execution claim is missing for this approved request."
            )
        else:
            execution = await self._claim_execution(request=request)
            if execution.status == "COMPLETED":
                if request.status != "COMPLETED":
                    request.status = "COMPLETED"
                    request.completed_at = execution.completed_at
                    await self.session.commit()
                return DeletionExecutionResult(
                    deletion_request_id=request.id,
                    approval_id=approval.id,
                    task_id=request.task_id,
                    status="COMPLETED",
                    already_executed=True,
                )
            if execution.status == "CANCELLED":
                if request.status != "CANCELLED":
                    request.status = "CANCELLED"
                    request.cancellation_reason = "fulfilled_elsewhere"
                    await self.session.commit()
                return DeletionExecutionResult(
                    deletion_request_id=request.id,
                    approval_id=approval.id,
                    task_id=request.task_id,
                    status="CANCELLED",
                )
            if execution.status == "FAILED":
                if request.status != "FAILED":
                    request.status = "FAILED"
                    request.failure_code = execution.failure_code
                    request.failure_message = execution.failure_message
                    await self.session.commit()
                raise InvalidApprovalStateError(
                    "The deletion execution has already failed permanently."
                )

        # An IN_PROGRESS record is a claim, not proof that deletion succeeded.
        # A missing task means another authorized path fulfilled the request.
        task = await self.session.get(Task, request.task_id)
        if task is None:
            request.status = "CANCELLED"
            request.cancellation_reason = "fulfilled_elsewhere"
            execution.status = "CANCELLED"
            await self.session.commit()
            return DeletionExecutionResult(
                deletion_request_id=request.id,
                approval_id=approval.id,
                task_id=request.task_id,
                status="CANCELLED",
            )

        request_id = request.id
        approval_id_value = approval.id
        task_id_value = request.task_id
        now = utc_now()

        try:
            # The durable IN_PROGRESS claim already exists. Task deletion,
            # request completion, and the ledger's COMPLETED transition commit
            # together in this second application-database transaction.
            await self.tasks.delete_task(task_id_value, commit=False)
            request.status = "COMPLETED"
            request.completed_at = now
            execution.status = "COMPLETED"
            execution.completed_at = now
            await self.session.flush()
        except Exception:
            await self.session.rollback()
            raise

        try:
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            return await self._reconcile_execution_after_commit_error(
                request_id=request_id,
                approval_id=approval_id_value,
                task_id=task_id_value,
                original_error=exc,
            )

        return DeletionExecutionResult(
            deletion_request_id=request_id,
            approval_id=approval_id_value,
            task_id=task_id_value,
            status="COMPLETED",
        )
