from collections.abc import AsyncIterator

import app.agent.deletion_executor as deletion_executor
import app.agent.nodes as agent_nodes
import app.agent.tool_executor as tool_executor
import app.tools.task_tools as task_tools
import pytest
import pytest_asyncio
from app.agent.graph import build_graph
from app.main import app
from app.models.deletion import DeletionApproval, DeletionRequest
from app.services import TaskService
from httpx import AsyncClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


class FakeChatModel:
    """Return predetermined LLM responses without calling Ollama."""

    def __init__(self, responses: list[AIMessage]):
        self.responses = list(responses)
        self.call_count = 0
        self.invocations = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages, config=None):
        self.call_count += 1
        # Keep a snapshot so later graph mutations cannot obscure diagnostics.
        self.invocations.append(list(messages))
        if not self.responses:
            raise AssertionError("FakeChatModel received more calls than expected.")
        return self.responses.pop(0)


def make_tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    """Build a deterministic AI tool-call response."""

    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def get_tool_result(messages, tool_name: str):
    """Return the ToolMessage for a named tool from a model invocation."""

    for message in reversed(messages):
        if getattr(message, "type", None) == "tool" and (
            getattr(message, "name", None) == tool_name
        ):
            return message
    raise AssertionError(
        f"No ToolMessage for tool {tool_name!r} was found in the captured turn."
    )


def assert_tool_succeeded(messages, tool_name: str) -> None:
    """Fail with the actual tool output if the graph reports a tool error."""

    result = get_tool_result(messages, tool_name)
    content = str(result.content)
    assert not getattr(result, "is_error", False), (
        f"Tool {tool_name!r} returned an error: {content}"
    )
    assert not content.startswith("Tool '") or " failed:" not in content, (
        f"Tool {tool_name!r} returned an error: {content}"
    )


@pytest_asyncio.fixture
async def e2e_api_client(
    api_client: AsyncClient,
    test_session_factory,
    monkeypatch,
    tmp_path,
) -> AsyncIterator[AsyncClient]:
    """Run the real API and graph against isolated databases."""

    monkeypatch.setattr(
        task_tools,
        "AsyncSessionLocal",
        test_session_factory,
    )
    monkeypatch.setattr(
        tool_executor,
        "AsyncSessionLocal",
        test_session_factory,
    )
    monkeypatch.setattr(
        deletion_executor,
        "AsyncSessionLocal",
        test_session_factory,
    )

    checkpoint_path = tmp_path / "e2e_checkpoints.db"

    async with AsyncSqliteSaver.from_conn_string(
        str(checkpoint_path)
    ) as checkpointer:
        await checkpointer.setup()
        app.state.graph = build_graph(checkpointer)

        try:
            yield api_client
        finally:
            app.state.graph = None


@pytest.mark.asyncio
async def test_task_crud_and_conversation_continuity(
    e2e_api_client: AsyncClient,
    test_session_factory,
    monkeypatch,
):
    """Exercise create, list, update, complete, and reopen in one conversation."""

    fake_model = FakeChatModel(
        [
            make_tool_call(
                "create_task",
                {
                    "title": "Prepare project documentation",
                    "description": "Document the TaskFlow AI architecture",
                    "priority": "high",
                },
                "call-create-1",
            ),
            AIMessage(content="The documentation task has been created."),
            make_tool_call(
                "list_tasks",
                {},
                "call-list-1",
            ),
            AIMessage(content="I found your documentation task."),
            make_tool_call(
                "update_task",
                {
                    "task_id": "__TASK_ID__",
                    "updates": {"priority": "low"},
                },
                "call-update-1",
            ),
            AIMessage(content="The task priority has been updated."),
            make_tool_call(
                "complete_task",
                {"task_id": "__TASK_ID__"},
                "call-complete-1",
            ),
            AIMessage(content="The task has been completed."),
            make_tool_call(
                "reopen_task",
                {"task_id": "__TASK_ID__"},
                "call-reopen-1",
            ),
            AIMessage(content="The task has been reopened."),
        ]
    )

    monkeypatch.setattr(
        agent_nodes,
        "create_chat_model",
        lambda: fake_model,
    )

    # 1. Create a task.
    response = await e2e_api_client.post(
        "/api/v1/chat",
        json={"message": "Create a high-priority documentation task."},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"

    thread_id = response.json()["thread_id"]

    async with test_session_factory() as session:
        tasks = await TaskService(session).list_tasks()

    assert len(tasks) == 1
    task_id = tasks[0].id

    assert tasks[0].title == "Prepare project documentation"
    assert tasks[0].priority == "high"
    assert tasks[0].status == "pending"
    assert_tool_succeeded(fake_model.invocations[1], "create_task")

    # Replace the placeholder task ID in the remaining fake tool calls.
    for response_item in fake_model.responses:
        for call in response_item.tool_calls:
            if call["args"].get("task_id") == "__TASK_ID__":
                call["args"]["task_id"] = task_id

    # 2. List tasks.
    response = await e2e_api_client.post(
        "/api/v1/chat",
        json={
            "thread_id": thread_id,
            "message": "List my tasks.",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert_tool_succeeded(fake_model.invocations[3], "list_tasks")

    # 3. Update task priority.
    response = await e2e_api_client.post(
        "/api/v1/chat",
        json={
            "thread_id": thread_id,
            "message": "Change the documentation task priority to low.",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert_tool_succeeded(fake_model.invocations[5], "update_task")

    async with test_session_factory() as session:
        tasks = await TaskService(session).list_tasks()

    assert len(tasks) == 1
    assert tasks[0].priority == "low"

    # 4. Complete task.
    response = await e2e_api_client.post(
        "/api/v1/chat",
        json={
            "thread_id": thread_id,
            "message": "Mark the documentation task as completed.",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert_tool_succeeded(fake_model.invocations[7], "complete_task")

    async with test_session_factory() as session:
        tasks = await TaskService(session).list_tasks()

    assert tasks[0].status == "completed"

    # 5. Reopen task.
    response = await e2e_api_client.post(
        "/api/v1/chat",
        json={
            "thread_id": thread_id,
            "message": "Reopen the documentation task.",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert_tool_succeeded(fake_model.invocations[9], "reopen_task")

    async with test_session_factory() as session:
        tasks = await TaskService(session).list_tasks()

    assert tasks[0].status == "pending"

    # Each request invokes the fake model once for the tool call and once
    # after tool execution.
    assert fake_model.call_count == 10
    assert fake_model.responses == []

    # Verify all five user/assistant exchanges were persisted.
    history_response = await e2e_api_client.get(
        f"/api/v1/chat/{thread_id}/history"
    )

    assert history_response.status_code == 200
    history = history_response.json()["messages"]

    assert len(history) == 10
    assert [message["role"] for message in history] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_approval", "task_should_exist"),
    [
        ("approve", "APPROVED", False),
        ("reject", "REJECTED", True),
    ],
)
async def test_deletion_approval_and_rejection_end_to_end(
    decision,
    expected_approval,
    task_should_exist,
    e2e_api_client: AsyncClient,
    test_session_factory,
    monkeypatch,
):
    """Verify durable deletion approval, rejection, and graph resumption."""

    fake_model = FakeChatModel(
        [
            # First request: create a task.
            make_tool_call(
                "create_task",
                {
                    "title": "Task requiring deletion",
                    "priority": "medium",
                },
                "call-create-delete-1",
            ),
            AIMessage(content="The task has been created."),
            # Second request: ask to delete the task.
            make_tool_call(
                "delete_task",
                {"task_id": "__TASK_ID__"},
                "call-delete-1",
            ),
            # Final response after the approval/rejection workflow resumes.
            AIMessage(
                content=(
                    "The task was deleted."
                    if decision == "approve"
                    else "The deletion was rejected. The task remains."
                )
            ),
        ]
    )

    monkeypatch.setattr(
        agent_nodes,
        "create_chat_model",
        lambda: fake_model,
    )

    # Create the task through the actual chat endpoint.
    create_response = await e2e_api_client.post(
        "/api/v1/chat",
        json={"message": "Create a task called Task requiring deletion."},
    )

    assert create_response.status_code == 200, create_response.text
    thread_id = create_response.json()["thread_id"]

    async with test_session_factory() as session:
        tasks = await TaskService(session).list_tasks()

    assert len(tasks) == 1
    task_id = tasks[0].id
    assert_tool_succeeded(fake_model.invocations[1], "create_task")

    # Set the real task ID in the pending fake delete tool call.
    delete_call = next(
        call
        for response_item in fake_model.responses
        for call in response_item.tool_calls
        if call["name"] == "delete_task"
    )
    delete_call["args"]["task_id"] = task_id

    # Request deletion through the real graph and tool executor.
    delete_response = await e2e_api_client.post(
        "/api/v1/chat",
        json={
            "thread_id": thread_id,
            "message": "Delete the task requiring deletion.",
        },
    )

    assert delete_response.status_code == 200, delete_response.text
    delete_data = delete_response.json()

    assert delete_data["status"] == "approval_required"
    pending = delete_data["pending_approval"]

    assert pending is not None
    assert pending["approval_id"]
    assert pending["deletion_request_id"]
    assert pending["task_id"] == task_id

    approval_id = pending["approval_id"]
    deletion_request_id = pending["deletion_request_id"]

    # A new message must not overwrite an unresolved approval.
    blocked_response = await e2e_api_client.post(
        "/api/v1/chat",
        json={
            "thread_id": thread_id,
            "message": "Create another task.",
        },
    )

    assert blocked_response.status_code == 409

    # Submit the real approval or rejection through FastAPI.
    approval_response = await e2e_api_client.post(
        f"/api/v1/chat/{thread_id}/approval",
        json={
            "approval_id": approval_id,
            "decision": decision,
        },
    )

    assert approval_response.status_code == 200, approval_response.text
    approval_data = approval_response.json()

    assert approval_data["status"] == "completed"
    assert approval_data["approval_id"] == approval_id
    assert approval_data["assistant_message"]

    # Verify durable approval records.
    async with test_session_factory() as session:
        approval = await session.get(DeletionApproval, approval_id)
        deletion_request = await session.get(
            DeletionRequest,
            deletion_request_id,
        )
        remaining_tasks = await TaskService(session).list_tasks()

    assert approval is not None
    assert approval.decision == expected_approval
    assert deletion_request is not None

    # Verify the actual task database state.
    if task_should_exist:
        assert any(task.id == task_id for task in remaining_tasks)
    else:
        assert all(task.id != task_id for task in remaining_tasks)

    # Verify the graph resumed and produced its final response.
    assert fake_model.call_count == 4
    assert fake_model.responses == []

    history_response = await e2e_api_client.get(
        f"/api/v1/chat/{thread_id}/history"
    )

    assert history_response.status_code == 200
    history = history_response.json()["messages"]

    assert len(history) == 5
    assert history[-1]["role"] == "assistant"
    assert history[-1]["content"] == approval_data["assistant_message"]
