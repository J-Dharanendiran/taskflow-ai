
"""Approved deletion execution for TaskFlow AI."""

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from app.agent.error_policy import (
    MAX_TRANSIENT_RETRIES,
    ErrorCategory,
    classify_error,
    should_retry,
)
from app.agent.state import AgentState
from app.agent.validators import validate_agent_state
from app.database.session import AsyncSessionLocal
from app.services.deletion_approval_service import DeletionApprovalService
from app.services.exceptions import UncertainExecutionOutcomeError


def _get_thread_id(config: RunnableConfig) -> str:
    """Read and validate the conversation thread ID."""

    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id")

    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("A valid thread_id is required for deletion execution.")

    return thread_id


def _build_deletion_result(
    *,
    pending: dict[str, str],
    content: str,
    is_error: bool = False,
) -> ToolMessage:
    """Build a result that replaces the original pending deletion result."""

    return ToolMessage(
        id=f"tool-result:{pending['tool_call_id']}",
        name="delete_task",
        tool_call_id=pending["tool_call_id"],
        content=content,
        status="error" if is_error else "success",
    )


async def _execute_approved_deletion(
    *,
    thread_id: str,
    approval_id: str,
):
    """Execute or reconcile deletion using a fresh database session."""

    async with AsyncSessionLocal() as session:
        service = DeletionApprovalService(session)

        return await service.execute_approved_deletion(
            thread_id=thread_id,
            approval_id=approval_id,
        )


async def _persist_terminal_failure(
    *,
    thread_id: str,
    approval_id: str,
    failure_code: str,
    failure_message: str,
) -> bool:
    """Persist failure only when the service confirms an eligible claim.

    Returns True only after the service successfully commits the failure.
    """

    async with AsyncSessionLocal() as session:
        service = DeletionApprovalService(session)

        await service.mark_execution_failed(
            thread_id=thread_id,
            approval_id=approval_id,
            failure_code=failure_code,
            failure_message=failure_message,
        )

    return True


async def _execute_with_retry(
    *,
    thread_id: str,
    approval_id: str,
):
    """Retry transient deletion failures against the same durable request."""

    retries_used = 0

    while True:
        try:
            return await _execute_approved_deletion(
                thread_id=thread_id,
                approval_id=approval_id,
            )

        except UncertainExecutionOutcomeError:
            # Never retry an outcome that cannot be safely reconciled.
            raise

        except Exception as error:
            if should_retry(
                error,
                retries_used=retries_used,
                max_retries=MAX_TRANSIENT_RETRIES,
            ):
                retries_used += 1
                continue

            category = classify_error(error)

            if category == ErrorCategory.TRANSIENT:
                failure_code = "TRANSIENT_RETRIES_EXHAUSTED"
            else:
                failure_code = f"{category.value.upper()}_DELETION_FAILURE"

            try:
                await _persist_terminal_failure(
                    thread_id=thread_id,
                    approval_id=approval_id,
                    failure_code=failure_code,
                    failure_message=str(error),
                )
            except UncertainExecutionOutcomeError:
                raise
            except Exception as persistence_error:
                raise RuntimeError(
                    "Deletion execution failed, but its terminal failure "
                    "could not be confirmed in the durable execution ledger. "
                    f"Execution error: {error}. "
                    f"Failure persistence error: {persistence_error}"
                ) from persistence_error

            raise RuntimeError(
                f"Deletion execution failed and was recorded as FAILED. "
                f"Failure code: {failure_code}. Error: {error}"
            ) from error


async def deletion_executor_node(
    state: AgentState,
    config: RunnableConfig,
) -> dict:
    """Execute a deletion after its approval has been persisted."""

    validate_agent_state(state)

    pending = state["pending_approval"]

    if pending is None:
        raise ValueError("Deletion Executor requires a pending approval.")

    if state["execution_status"] != "waiting_for_approval":
        raise ValueError(
            "Deletion Executor requires waiting_for_approval status."
        )

    thread_id = _get_thread_id(config)

    try:
        result = await _execute_with_retry(
            thread_id=thread_id,
            approval_id=pending["approval_id"],
        )

        result_status = str(result.status).lower()

        if result_status == "completed":
            if result.already_executed:
                content = (
                    "The task deletion had already been completed. "
                    "No duplicate deletion was performed."
                )
            else:
                content = (
                    f"Task {result.task_id} was successfully deleted."
                )

            tool_message = _build_deletion_result(
                pending=pending,
                content=content,
            )

        elif result_status == "cancelled":
            tool_message = _build_deletion_result(
                pending=pending,
                content=(
                    f"Task {result.task_id} no longer exists. "
                    "The deletion request was reconciled as already fulfilled; "
                    "this execution did not delete the task."
                ),
            )

        else:
            tool_message = _build_deletion_result(
                pending=pending,
                content=(
                    "Deletion was not confirmed. "
                    f"The deletion service reported status: {result_status}."
                ),
                is_error=True,
            )

    except UncertainExecutionOutcomeError:
        tool_message = _build_deletion_result(
            pending=pending,
            content=(
                "The deletion outcome is uncertain. "
                "The durable execution record must be reconciled before "
                "attempting another deletion. Do not assume the task was deleted."
            ),
            is_error=True,
        )

    except Exception as error:
        tool_message = _build_deletion_result(
            pending=pending,
            content=f"Approved deletion failed: {error}",
            is_error=True,
        )

    return {
        "messages": [tool_message],
        "pending_approval": None,
        "execution_status": "running",
    }
