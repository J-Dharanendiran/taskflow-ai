from types import SimpleNamespace

import pytest
from app.main import app
from app.models.deletion import DeletionApproval, DeletionRequest
from app.models.task import Task
from app.services.conversation_service import ConversationService
from langchain_core.messages import AIMessage
from sqlalchemy import select


@pytest.mark.asyncio
async def test_get_history_returns_persisted_messages(
    api_client,
    test_session_factory,
):
    async with test_session_factory() as session:
        service = ConversationService(session)

        await service.create_conversation("thread-history")
        await service.add_message(
            "thread-history", "user", "Create a task"
        )
        await service.add_message(
            "thread-history", "assistant", "What should the task be?"
        )

    response = await api_client.get(
        "/api/v1/chat/thread-history/history"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["thread_id"] == "thread-history"
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Create a task"
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["content"] == "What should the task be?"
    assert data["has_more"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_history_returns_404_for_missing_conversation(
    api_client,
):
    response = await api_client.get(
        "/api/v1/chat/missing-thread/history"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_history_rejects_invalid_limit(api_client):
    response = await api_client.get(
        "/api/v1/chat/thread-history/history",
        params={"limit": 101},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_history_rejects_invalid_cursor(
    api_client,
    test_session_factory,
):
    async with test_session_factory() as session:
        service = ConversationService(session)
        await service.create_conversation("thread-history")

    response = await api_client.get(
        "/api/v1/chat/thread-history/history",
        params={"cursor": "invalid-cursor"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_history_supports_cursor_pagination(
    api_client,
    test_session_factory,
):
    async with test_session_factory() as session:
        service = ConversationService(session)

        await service.create_conversation("thread-history")

        for index in range(1, 4):
            await service.add_message(
                "thread-history",
                "user",
                f"Message {index}",
            )

    first_response = await api_client.get(
        "/api/v1/chat/thread-history/history",
        params={"limit": 2},
    )

    assert first_response.status_code == 200

    first_page = first_response.json()

    assert len(first_page["messages"]) == 2
    assert first_page["has_more"] is True
    assert first_page["next_cursor"] is not None

    second_response = await api_client.get(
        "/api/v1/chat/thread-history/history",
        params={
            "limit": 2,
            "cursor": first_page["next_cursor"],
        },
    )

    assert second_response.status_code == 200

    second_page = second_response.json()

    assert len(second_page["messages"]) == 1
    assert second_page["messages"][0]["content"] == "Message 3"
    assert second_page["has_more"] is False
    assert second_page["next_cursor"] is None


@pytest.mark.asyncio
async def test_chat_returns_completed_response(
    api_client,
    test_session_factory,
    monkeypatch,
):
    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(
                values={},
                interrupts=(),
            )

        async def ainvoke(self, state, config):
            return {
                "execution_status": "completed",
                "messages": [
                    *state["messages"],
                    AIMessage(content="Your tasks are up to date."),
                ],
            }

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        "/api/v1/chat",
        json={"message": "Show my tasks"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "completed"
    assert data["assistant_message"] == "Your tasks are up to date."
    assert data["thread_id"]
    assert data["message_id"]
    assert data["pending_approval"] is None

    async with test_session_factory() as session:
        history = await ConversationService(session).get_history(
            data["thread_id"]
        )

    assert len(history["messages"]) == 2
    assert history["messages"][0]["role"] == "user"
    assert history["messages"][0]["content"] == "Show my tasks"
    assert history["messages"][1]["role"] == "assistant"
    assert (
        history["messages"][1]["content"]
        == "Your tasks are up to date."
    )

@pytest.mark.asyncio
async def test_chat_returns_clarification_required_response(
    api_client,
    test_session_factory,
    monkeypatch,
):
    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={}, interrupts=())

        async def ainvoke(self, state, config):
            return {
                "execution_status": "waiting_for_clarification",
                "messages": [
                    *state["messages"],
                    AIMessage(
                        content="What date should I schedule the task for?"
                    ),
                ],
            }

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        "/api/v1/chat",
        json={"message": "Remind me to submit my assignment"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "clarification_required"
    assert (
        data["assistant_message"]
        == "What date should I schedule the task for?"
    )
    assert data["pending_approval"] is None

    async with test_session_factory() as session:
        history = await ConversationService(session).get_history(
            data["thread_id"]
        )

    assert len(history["messages"]) == 2
    assert history["messages"][1]["content"] == (
        "What date should I schedule the task for?"
    )

@pytest.mark.asyncio
async def test_chat_returns_approval_required_response(
    api_client,
    test_session_factory,
    monkeypatch,
):
    approval_message = (
        "Human approval is required before deleting this task."
    )

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={}, interrupts=())

        async def ainvoke(self, state, config):
            return {
                "execution_status": "waiting_for_approval",
                "messages": state["messages"],
                "pending_approval": {
                    "approval_id": "approval-test-1",
                    "deletion_request_id": "deletion-test-1",
                    "task_id": "task-test-1",
                    "tool_call_id": "call-delete-1",
                },
                "__interrupt__": [
                    SimpleNamespace(
                        value={
                            "type": "deletion_approval",
                            "approval_id": "approval-test-1",
                            "deletion_request_id": "deletion-test-1",
                            "task_id": "task-test-1",
                            "message": approval_message,
                        }
                    )
                ],
            }

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        "/api/v1/chat",
        json={"message": "Delete task task-test-1"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "approval_required"
    assert data["assistant_message"] == approval_message
    assert data["pending_approval"] == {
        "approval_id": "approval-test-1",
        "deletion_request_id": "deletion-test-1",
        "task_id": "task-test-1",
        "message": approval_message,
    }

    async with test_session_factory() as session:
        history = await ConversationService(session).get_history(
            data["thread_id"]
        )

    assert len(history["messages"]) == 2
    assert history["messages"][1]["content"] == approval_message


@pytest.mark.asyncio
async def test_approval_endpoint_persists_decision_and_resumes_graph(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-approval-test"
    task_id = "task-approval-test"
    deletion_request_id = "deletion-approval-test"
    approval_id = "approval-approval-test"

    approval_message = "Human approval is required before deleting this task."
    assistant_message = "The task was successfully deleted."

    # Seed the actual database records.
    async with test_session_factory() as session:
        service = ConversationService(session)
        await service.create_conversation(thread_id)

        task = Task(
            id=task_id,
            title="Task to delete",
        )

        deletion_request = DeletionRequest(
            id=deletion_request_id,
            task_id=task_id,
            task_title_snapshot="Task to delete",
            thread_id=thread_id,
            execution_id="execution-approval-test",
            tool_call_id="call-approval-test",
            status="PENDING",
        )

        approval = DeletionApproval(
            id=approval_id,
            deletion_request_id=deletion_request_id,
            thread_id=thread_id,
            execution_id="execution-approval-test",
            tool_call_id="call-approval-test",
            decision="PENDING",
        )

        session.add_all([task, deletion_request, approval])
        await session.commit()

    class FakeGraph:
        async def aget_state(self, config):
            assert config["configurable"]["thread_id"] == thread_id

            return SimpleNamespace(
                values={},
                interrupts=(
                    SimpleNamespace(
                        value={
                            "type": "deletion_approval",
                            "approval_id": approval_id,
                            "deletion_request_id": deletion_request_id,
                            "task_id": task_id,
                            "message": approval_message,
                        }
                    ),
                ),
            )

        async def ainvoke(self, command, config):
            assert command.resume == {
                "approval_id": approval_id,
                "approved": True,
            }
            assert config["configurable"]["thread_id"] == thread_id

            return {
                "execution_status": "completed",
                "messages": [
                    AIMessage(content=assistant_message),
                ],
            }

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": "approve",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["thread_id"] == thread_id
    assert data["approval_id"] == approval_id
    assert data["status"] == "completed"
    assert data["assistant_message"] == assistant_message

    # Verify the durable approval decision was committed.
    async with test_session_factory() as session:
        saved_approval = await session.scalar(
            select(DeletionApproval).where(
                DeletionApproval.id == approval_id
            )
        )

        saved_request = await session.scalar(
            select(DeletionRequest).where(
                DeletionRequest.id == deletion_request_id
            )
        )

        history = await ConversationService(session).get_history(
            thread_id
        )

    assert saved_approval.decision == "APPROVED"
    assert saved_request.status == "APPROVED"

    assert len(history["messages"]) == 1
    assert history["messages"][0]["role"] == "assistant"
    assert history["messages"][0]["content"] == assistant_message


@pytest.mark.asyncio
async def test_approval_endpoint_persists_rejection_and_resumes_graph(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-rejection-test"
    task_id = "task-rejection-test"
    deletion_request_id = "deletion-rejection-test"
    approval_id = "approval-rejection-test"

    assistant_message = "The deletion request was rejected."

    async with test_session_factory() as session:
        await ConversationService(session).create_conversation(thread_id)

        session.add_all([
            Task(id=task_id, title="Task to keep"),
            DeletionRequest(
                id=deletion_request_id,
                task_id=task_id,
                task_title_snapshot="Task to keep",
                thread_id=thread_id,
                execution_id="execution-rejection-test",
                tool_call_id="call-rejection-test",
                status="PENDING",
            ),
            DeletionApproval(
                id=approval_id,
                deletion_request_id=deletion_request_id,
                thread_id=thread_id,
                execution_id="execution-rejection-test",
                tool_call_id="call-rejection-test",
                decision="PENDING",
            ),
        ])
        await session.commit()

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(
                values={},
                interrupts=(
                    SimpleNamespace(
                        value={
                            "type": "deletion_approval",
                            "approval_id": approval_id,
                            "deletion_request_id": deletion_request_id,
                            "task_id": task_id,
                            "message": "Approval required.",
                        }
                    ),
                ),
            )

        async def ainvoke(self, command, config):
            assert command.resume == {
                "approval_id": approval_id,
                "approved": False,
            }

            return {
                "execution_status": "completed",
                "messages": [
                    AIMessage(content=assistant_message),
                ],
            }

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": "reject",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "completed"
    assert data["assistant_message"] == assistant_message

    async with test_session_factory() as session:
        saved_approval = await session.scalar(
            select(DeletionApproval).where(
                DeletionApproval.id == approval_id
            )
        )
        saved_request = await session.scalar(
            select(DeletionRequest).where(
                DeletionRequest.id == deletion_request_id
            )
        )
        saved_task = await session.get(Task, task_id)

    assert saved_approval.decision == "REJECTED"
    assert saved_request.status == "REJECTED"
    assert saved_task is not None


@pytest.mark.asyncio
async def test_repeated_rejection_does_not_resume_graph_twice(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-idempotency-test"
    task_id = "task-idempotency-test"
    deletion_request_id = "deletion-idempotency-test"
    approval_id = "approval-idempotency-test"

    async with test_session_factory() as session:
        await ConversationService(session).create_conversation(thread_id)

        session.add_all([
            Task(id=task_id, title="Keep this task"),
            DeletionRequest(
                id=deletion_request_id,
                task_id=task_id,
                task_title_snapshot="Keep this task",
                thread_id=thread_id,
                execution_id="execution-idempotency-test",
                tool_call_id="call-idempotency-test",
                status="PENDING",
            ),
            DeletionApproval(
                id=approval_id,
                deletion_request_id=deletion_request_id,
                thread_id=thread_id,
                execution_id="execution-idempotency-test",
                tool_call_id="call-idempotency-test",
                decision="PENDING",
            ),
        ])
        await session.commit()

    class FakeGraph:
        def __init__(self):
            self.resumed = False
            self.resume_count = 0

        async def aget_state(self, config):
            interrupts = ()

            if not self.resumed:
                interrupts = (
                    SimpleNamespace(
                        value={
                            "type": "deletion_approval",
                            "approval_id": approval_id,
                            "deletion_request_id": deletion_request_id,
                            "task_id": task_id,
                            "message": "Approval required.",
                        }
                    ),
                )

            return SimpleNamespace(
                values={},
                interrupts=interrupts,
            )

        async def ainvoke(self, command, config):
            self.resume_count += 1
            self.resumed = True

            assert command.resume == {
                "approval_id": approval_id,
                "approved": False,
            }

            return {
                "execution_status": "completed",
                "messages": [
                    AIMessage(
                        content="The deletion request was rejected."
                    ),
                ],
            }

    fake_graph = FakeGraph()

    monkeypatch.setattr(
        app.state,
        "graph",
        fake_graph,
        raising=False,
    )

    payload = {
        "approval_id": approval_id,
        "decision": "reject",
    }

    first_response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json=payload,
    )

    assert first_response.status_code == 200
    assert fake_graph.resume_count == 1

    second_response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json=payload,
    )

    assert second_response.status_code == 200
    assert fake_graph.resume_count == 1

    async with test_session_factory() as session:
        saved_approval = await session.get(
            DeletionApproval,
            approval_id,
        )
        saved_request = await session.get(
            DeletionRequest,
            deletion_request_id,
        )

    assert saved_approval.decision == "REJECTED"
    assert saved_request.status == "REJECTED"


@pytest.mark.asyncio
async def test_conflicting_approval_decision_returns_409(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-conflict-test"
    task_id = "task-conflict-test"
    deletion_request_id = "deletion-conflict-test"
    approval_id = "approval-conflict-test"

    async with test_session_factory() as session:
        await ConversationService(session).create_conversation(thread_id)

        session.add_all([
            Task(id=task_id, title="Conflict test task"),
            DeletionRequest(
                id=deletion_request_id,
                task_id=task_id,
                task_title_snapshot="Conflict test task",
                thread_id=thread_id,
                execution_id="execution-conflict-test",
                tool_call_id="call-conflict-test",
                status="PENDING",
            ),
            DeletionApproval(
                id=approval_id,
                deletion_request_id=deletion_request_id,
                thread_id=thread_id,
                execution_id="execution-conflict-test",
                tool_call_id="call-conflict-test",
                decision="PENDING",
            ),
        ])
        await session.commit()

    class FakeGraph:
        def __init__(self):
            self.resumed = False
            self.resume_count = 0

        async def aget_state(self, config):
            interrupts = ()

            if not self.resumed:
                interrupts = (
                    SimpleNamespace(
                        value={
                            "type": "deletion_approval",
                            "approval_id": approval_id,
                            "deletion_request_id": deletion_request_id,
                            "task_id": task_id,
                            "message": "Approval required.",
                        }
                    ),
                )

            return SimpleNamespace(
                values={},
                interrupts=interrupts,
            )

        async def ainvoke(self, command, config):
            self.resume_count += 1
            self.resumed = True

            assert command.resume == {
                "approval_id": approval_id,
                "approved": False,
            }

            return {
                "execution_status": "completed",
                "messages": [
                    AIMessage(
                        content="The deletion request was rejected."
                    ),
                ],
            }

    fake_graph = FakeGraph()

    monkeypatch.setattr(
        app.state,
        "graph",
        fake_graph,
        raising=False,
    )

    first_response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": "reject",
        },
    )

    assert first_response.status_code == 200

    conflicting_response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": "approve",
        },
    )

    assert conflicting_response.status_code == 409
    assert fake_graph.resume_count == 1

    async with test_session_factory() as session:
        saved_approval = await session.get(
            DeletionApproval,
            approval_id,
        )
        saved_request = await session.get(
            DeletionRequest,
            deletion_request_id,
        )

    assert saved_approval.decision == "REJECTED"
    assert saved_request.status == "REJECTED"


@pytest.mark.asyncio
async def test_approval_from_wrong_thread_returns_404(
    api_client,
    test_session_factory,
    monkeypatch,
):
    original_thread_id = "thread-original-test"
    wrong_thread_id = "thread-wrong-test"
    task_id = "task-wrong-thread-test"
    deletion_request_id = "deletion-wrong-thread-test"
    approval_id = "approval-wrong-thread-test"

    async with test_session_factory() as session:
        service = ConversationService(session)
        await service.create_conversation(original_thread_id)
        await service.create_conversation(wrong_thread_id)

        session.add_all([
            Task(id=task_id, title="Protected task"),
            DeletionRequest(
                id=deletion_request_id,
                task_id=task_id,
                task_title_snapshot="Protected task",
                thread_id=original_thread_id,
                execution_id="execution-wrong-thread-test",
                tool_call_id="call-wrong-thread-test",
                status="PENDING",
            ),
            DeletionApproval(
                id=approval_id,
                deletion_request_id=deletion_request_id,
                thread_id=original_thread_id,
                execution_id="execution-wrong-thread-test",
                tool_call_id="call-wrong-thread-test",
                decision="PENDING",
            ),
        ])
        await session.commit()

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={}, interrupts=())

        async def ainvoke(self, command, config):
            pytest.fail("Graph must not resume for a wrong-thread approval.")

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        f"/api/v1/chat/{wrong_thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": "approve",
        },
    )

    assert response.status_code == 404

    async with test_session_factory() as session:
        saved_approval = await session.get(
            DeletionApproval,
            approval_id,
        )

    assert saved_approval.decision == "PENDING"

@pytest.mark.asyncio
async def test_unknown_approval_id_returns_404(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-unknown-approval-test"

    async with test_session_factory() as session:
        service = ConversationService(session)
        await service.create_conversation(thread_id)

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={}, interrupts=())

        async def ainvoke(self, command, config):
            pytest.fail("Graph must not resume for an unknown approval ID.")

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": "approval-does-not-exist",
            "decision": "approve",
        },
    )

    assert response.status_code == 404

async def _seed_approval_records(
    session,
    *,
    thread_id,
    task_id,
    deletion_request_id,
    approval_id,
    approval_decision="PENDING",
    request_status="PENDING",
):
    await ConversationService(session).create_conversation(thread_id)

    session.add_all([
        Task(
            id=task_id,
            title="Test deletion task",
        ),
        DeletionRequest(
            id=deletion_request_id,
            task_id=task_id,
            task_title_snapshot="Test deletion task",
            thread_id=thread_id,
            execution_id=f"execution-{approval_id}",
            tool_call_id=f"call-{approval_id}",
            status=request_status,
        ),
        DeletionApproval(
            id=approval_id,
            deletion_request_id=deletion_request_id,
            thread_id=thread_id,
            execution_id=f"execution-{approval_id}",
            tool_call_id=f"call-{approval_id}",
            decision=approval_decision,
        ),
    ])

    await session.commit()


@pytest.mark.asyncio
async def test_chat_returns_503_when_graph_is_unavailable(
    api_client,
    monkeypatch,
):
    monkeypatch.setattr(
        app.state,
        "graph",
        None,
        raising=False,
    )

    response = await api_client.post(
        "/api/v1/chat",
        json={"message": "Show my tasks"},
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_chat_returns_404_for_missing_conversation(
    api_client,
    monkeypatch,
):
    class FakeGraph:
        async def aget_state(self, config):
            pytest.fail("Graph must not be accessed for a missing conversation.")

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        "/api/v1/chat",
        json={
            "thread_id": "missing-chat-thread",
            "message": "Show my tasks",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_chat_rejects_new_message_while_approval_is_pending(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-pending-chat-test"

    async with test_session_factory() as session:
        await ConversationService(session).create_conversation(thread_id)

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(
                values={
                    "execution_status": "waiting_for_approval",
                },
                interrupts=(),
            )

        async def ainvoke(self, state, config):
            pytest.fail("Graph must not execute while approval is pending.")

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        "/api/v1/chat",
        json={
            "thread_id": thread_id,
            "message": "Create another task",
        },
    )

    assert response.status_code == 409

    async with test_session_factory() as session:
        history = await ConversationService(session).get_history(thread_id)

    assert history["messages"] == []



@pytest.mark.asyncio
async def test_chat_persists_assistant_message_when_graph_fails(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-failed-chat-test"
    error_message = "The task operation failed."

    async with test_session_factory() as session:
        await ConversationService(session).create_conversation(thread_id)

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={}, interrupts=())

        async def ainvoke(self, state, config):
            return {
                "execution_status": "failed",
                "messages": [
                    *state["messages"],
                    AIMessage(content=error_message),
                ],
            }

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        "/api/v1/chat",
        json={
            "thread_id": thread_id,
            "message": "Create a task",
        },
    )

    assert response.status_code == 502

    async with test_session_factory() as session:
        history = await ConversationService(session).get_history(thread_id)

    assert len(history["messages"]) == 2
    assert history["messages"][0]["content"] == "Create a task"
    assert history["messages"][1]["content"] == error_message


@pytest.mark.asyncio
async def test_approval_returns_404_for_missing_conversation(
    api_client,
    monkeypatch,
):
    class FakeGraph:
        async def aget_state(self, config):
            pytest.fail("Graph must not be accessed for a missing conversation.")

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        "/api/v1/chat/missing-approval-thread/approval",
        json={
            "approval_id": "approval-missing-thread",
            "decision": "approve",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pending_approval_without_active_interrupt_returns_409(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-no-interrupt-test"
    task_id = "task-no-interrupt-test"
    deletion_request_id = "deletion-no-interrupt-test"
    approval_id = "approval-no-interrupt-test"

    async with test_session_factory() as session:
        await _seed_approval_records(
            session,
            thread_id=thread_id,
            task_id=task_id,
            deletion_request_id=deletion_request_id,
            approval_id=approval_id,
        )

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={}, interrupts=())

        async def ainvoke(self, command, config):
            pytest.fail("Graph must not resume without an active interrupt.")

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": "approve",
        },
    )

    assert response.status_code == 409

    async with test_session_factory() as session:
        saved_approval = await session.get(DeletionApproval, approval_id)

    assert saved_approval.decision == "PENDING"


@pytest.mark.asyncio
async def test_completed_approval_retry_returns_recorded_result(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-completed-retry-test"
    task_id = "task-completed-retry-test"
    deletion_request_id = "deletion-completed-retry-test"
    approval_id = "approval-completed-retry-test"

    async with test_session_factory() as session:
        await _seed_approval_records(
            session,
            thread_id=thread_id,
            task_id=task_id,
            deletion_request_id=deletion_request_id,
            approval_id=approval_id,
            approval_decision="APPROVED",
            request_status="COMPLETED",
        )

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={}, interrupts=())

        async def ainvoke(self, command, config):
            pytest.fail("Completed approval retries must not resume the graph.")

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": "approve",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["assistant_message"] == (
        "The task was successfully deleted."
    )


@pytest.mark.asyncio
async def test_approved_but_nonterminal_deletion_returns_409(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-nonterminal-test"
    task_id = "task-nonterminal-test"
    deletion_request_id = "deletion-nonterminal-test"
    approval_id = "approval-nonterminal-test"

    async with test_session_factory() as session:
        await _seed_approval_records(
            session,
            thread_id=thread_id,
            task_id=task_id,
            deletion_request_id=deletion_request_id,
            approval_id=approval_id,
            approval_decision="APPROVED",
            request_status="APPROVED",
        )

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={}, interrupts=())

        async def ainvoke(self, command, config):
            pytest.fail("Unresolved approval must not be blindly resumed.")

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": "approve",
        },
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_failed_deletion_returns_502_on_approval_retry(
    api_client,
    test_session_factory,
    monkeypatch,
):
    thread_id = "thread-failed-deletion-test"
    task_id = "task-failed-deletion-test"
    deletion_request_id = "deletion-failed-deletion-test"
    approval_id = "approval-failed-deletion-test"

    async with test_session_factory() as session:
        await _seed_approval_records(
            session,
            thread_id=thread_id,
            task_id=task_id,
            deletion_request_id=deletion_request_id,
            approval_id=approval_id,
            approval_decision="APPROVED",
            request_status="FAILED",
        )

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={}, interrupts=())

        async def ainvoke(self, command, config):
            pytest.fail("A failed deletion must not be blindly retried.")

    monkeypatch.setattr(
        app.state,
        "graph",
        FakeGraph(),
        raising=False,
    )

    response = await api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": "approve",
        },
    )

    assert response.status_code == 502


