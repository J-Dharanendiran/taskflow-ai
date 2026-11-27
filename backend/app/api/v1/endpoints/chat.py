
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import create_initial_state
from app.database.dependencies import get_db
from app.models.deletion import DeletionApproval, DeletionRequest
from app.schemas.chat import (
    ApprovalRequest,
    ApprovalResponse,
    ChatRequest,
    ChatResponse,
    ChatStatus,
    HistoryResponse,
    PendingApprovalResponse,
)
from app.services.conversation_service import ConversationService
from app.services.deletion_approval_service import DeletionApprovalService
from app.services.exceptions import (
    ApprovalConflictError,
    ApprovalNotFoundError,
    ConversationNotFoundError,
    InvalidApprovalStateError,
    InvalidConversationDataError,
    UncertainExecutionOutcomeError,
)

router = APIRouter()

RECENT_MESSAGE_LIMIT = ConversationService.DEFAULT_PAGE_SIZE


def _to_langchain_message(message):
    """Convert a persisted conversation message into a LangChain message."""
    if message.role == "user":
        return HumanMessage(content=message.content, id=message.id)

    return AIMessage(content=message.content, id=message.id)


def _get_assistant_message(messages) -> str:
    """Return the latest user-visible assistant response."""
    for message in reversed(messages):
        if (
            isinstance(message, AIMessage)
            and not message.tool_calls
            and isinstance(message.content, str)
            and message.content.strip()
        ):
            return message.content

    raise RuntimeError("The agent did not produce an assistant response.")


def _get_interrupt_for_approval(snapshot, approval_id: str):
    """Find the active deletion approval interrupt for an approval ID."""
    for interrupt in snapshot.interrupts:
        value = interrupt.value

        if (
            isinstance(value, dict)
            and value.get("type") == "deletion_approval"
            and value.get("approval_id") == approval_id
        ):
            return interrupt

    return None


def _status_value(value) -> str:
    """Normalize a string or enum status to its string value."""
    return str(getattr(value, "value", value)).upper()


def _approval_response(
    thread_id: str,
    approval_id: str,
    assistant_message: str,
) -> ApprovalResponse:
    """Build the stable response for a completed approval decision."""
    return ApprovalResponse(
        thread_id=thread_id,
        approval_id=approval_id,
        status="completed",
        assistant_message=assistant_message,
    )


def _raise_approval_service_error(error: Exception) -> None:
    """Translate approval-service exceptions into HTTP responses."""
    if isinstance(error, ApprovalNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if isinstance(error, ApprovalConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(error, InvalidApprovalStateError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(error, UncertainExecutionOutcomeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The deletion outcome is uncertain. "
                "Check the conversation before retrying."
            ),
        ) from error

    raise error


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
)
async def chat(
    payload: ChatRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Execute a user message through the TaskFlow AI graph."""
    graph = getattr(request.app.state, "graph", None)

    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The TaskFlow AI agent is not initialized.",
        )

    conversation_service = ConversationService(session)
    thread_id = payload.thread_id or str(uuid4())

    try:
        # Create a new conversation or validate the existing one.
        if payload.thread_id is None:
            await conversation_service.create_conversation(thread_id)
        else:
            await conversation_service.get_conversation(thread_id)

        graph_config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        # Prevent a new message from overwriting an unresolved approval.
        snapshot = await graph.aget_state(graph_config)
        snapshot_values = snapshot.values or {}

        has_active_approval = any(
            isinstance(interrupt.value, dict)
            and interrupt.value.get("type") == "deletion_approval"
            for interrupt in snapshot.interrupts
        )

        is_waiting_for_approval = (
            snapshot_values.get("execution_status") == "waiting_for_approval"
        )

        if has_active_approval or is_waiting_for_approval:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This conversation has a pending approval. "
                    "Resolve it before sending another message."
                ),
            )

        # Load previous messages before saving the current user message.
        # This prevents the current message from being included twice.
        recent_messages = await conversation_service.get_recent_messages(
            thread_id,
            limit=RECENT_MESSAGE_LIMIT,
        )

        user_message = await conversation_service.add_message(
            thread_id=thread_id,
            role="user",
            content=payload.message,
        )

        graph_messages = [
            _to_langchain_message(message)
            for message in recent_messages
        ]
        graph_messages.append(_to_langchain_message(user_message))

        initial_state = create_initial_state(
            execution_id=str(uuid4()),
            messages=graph_messages,
        )

        result = await graph.ainvoke(
            initial_state,
            config=graph_config,
        )

        execution_status = result["execution_status"]

        if execution_status == "failed":
            assistant_message = _get_assistant_message(result["messages"])

            await conversation_service.add_message(
                thread_id=thread_id,
                role="assistant",
                content=assistant_message,
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=assistant_message,
            )

        pending_approval = None
        interrupts = result.get("__interrupt__", ())

        if interrupts:
            interrupt_value = interrupts[0].value

            if (
                not isinstance(interrupt_value, dict)
                or interrupt_value.get("type") != "deletion_approval"
            ):
                raise RuntimeError("The graph returned an unexpected interrupt.")

            pending = result.get("pending_approval")

            if not pending:
                raise RuntimeError(
                    "The graph interrupted without pending approval state."
                )

            response_status: ChatStatus = "approval_required"
            assistant_message = interrupt_value["message"]

            pending_approval = PendingApprovalResponse(
                approval_id=pending["approval_id"],
                deletion_request_id=pending["deletion_request_id"],
                task_id=pending["task_id"],
                message=assistant_message,
            )

        elif execution_status == "waiting_for_clarification":
            response_status = "clarification_required"
            assistant_message = _get_assistant_message(result["messages"])

        elif execution_status == "completed":
            response_status = "completed"
            assistant_message = _get_assistant_message(result["messages"])

        else:
            raise RuntimeError(
                f"Unexpected graph execution status: {execution_status}"
            )

        assistant_record = await conversation_service.add_message(
            thread_id=thread_id,
            role="assistant",
            content=assistant_message,
        )

        return ChatResponse(
            thread_id=thread_id,
            message_id=assistant_record.id,
            status=response_status,
            assistant_message=assistant_message,
            pending_approval=pending_approval,
        )

    except HTTPException:
        raise

    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except InvalidConversationDataError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.post(
    "/chat/{thread_id}/approval",
    response_model=ApprovalResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_approval(
    thread_id: str,
    payload: ApprovalRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ApprovalResponse:
    """Record a deletion decision and resume the interrupted graph."""
    graph = getattr(request.app.state, "graph", None)

    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The TaskFlow AI agent is not initialized.",
        )

    conversation_service = ConversationService(session)
    approval_service = DeletionApprovalService(session)

    try:
        await conversation_service.get_conversation(thread_id)

        graph_config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        snapshot = await graph.aget_state(graph_config)
        approval_interrupt = _get_interrupt_for_approval(
            snapshot,
            payload.approval_id,
        )

        # Load the durable approval record. The database, not the graph
        # checkpoint, is authoritative for the approval decision.
        approval = await session.scalar(
            select(DeletionApproval).where(
                DeletionApproval.id == payload.approval_id,
                DeletionApproval.thread_id == thread_id,
            )
        )

        if approval is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The requested approval was not found.",
            )

        approved = payload.decision == "approve"
        expected_decision = "APPROVED" if approved else "REJECTED"
        current_decision = _status_value(approval.decision)

        # No active interrupt means this may be a retry after the graph
        # already completed. Only an identical previously saved decision
        # is allowed to take this path.
        if approval_interrupt is None:
            if current_decision == "PENDING":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "There is no active graph interrupt for this approval. "
                        "The approval cannot be processed safely."
                    ),
                )

            if current_decision != expected_decision:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A conflicting decision has already been recorded.",
                )

            deletion_request = await session.get(
                DeletionRequest,
                approval.deletion_request_id,
            )

            if deletion_request is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="The associated deletion request was not found.",
                )

            request_status = _status_value(deletion_request.status)

            if request_status == "COMPLETED":
                return _approval_response(
                    thread_id,
                    payload.approval_id,
                    "The task was successfully deleted.",
                )

            if request_status == "REJECTED":
                return _approval_response(
                    thread_id,
                    payload.approval_id,
                    "Deletion was rejected. The task was not deleted.",
                )

            if request_status == "FAILED":
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "The deletion operation failed. "
                        "The recorded outcome must be investigated."
                    ),
                )

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The approval decision is recorded, but the graph "
                    "has not reached a confirmed terminal state."
                ),
            )

        # The graph has the matching active interrupt. Persist the decision
        # before resuming, so retries cannot silently change the decision.
        await approval_service.decide(
            thread_id=thread_id,
            approval_id=payload.approval_id,
            approved=approved,
        )

        result = await graph.ainvoke(
            Command(
                resume={
                    "approval_id": payload.approval_id,
                    "approved": approved,
                }
            ),
            config=graph_config,
        )

        execution_status = result["execution_status"]

        if execution_status == "failed":
            assistant_message = _get_assistant_message(result["messages"])

            await conversation_service.add_message(
                thread_id=thread_id,
                role="assistant",
                content=assistant_message,
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=assistant_message,
            )

        if result.get("__interrupt__"):
            raise RuntimeError(
                "The graph returned another interrupt while processing approval."
            )

        if execution_status != "completed":
            raise RuntimeError(
                "The graph did not complete after processing the approval."
            )

        assistant_message = _get_assistant_message(result["messages"])

        await conversation_service.add_message(
            thread_id=thread_id,
            role="assistant",
            content=assistant_message,
        )

        return _approval_response(
            thread_id,
            payload.approval_id,
            assistant_message,
        )

    except HTTPException:
        raise

    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except (
        ApprovalConflictError,
        ApprovalNotFoundError,
        InvalidApprovalStateError,
        UncertainExecutionOutcomeError,
    ) as error:
        _raise_approval_service_error(error)

    except InvalidConversationDataError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get(
    "/chat/{thread_id}/history",
    response_model=HistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_chat_history(
    thread_id: str,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> HistoryResponse:
    """Return chronological conversation history with cursor pagination."""
    conversation_service = ConversationService(session)

    try:
        await conversation_service.get_conversation(thread_id)

        history = await conversation_service.get_history(
            thread_id=thread_id,
            limit=limit,
            cursor=cursor,
        )

        return HistoryResponse(**history)

    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except InvalidConversationDataError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

