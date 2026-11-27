import app.agent.tool_executor as tool_executor
from app.agent.graph import build_graph
from app.agent.state import create_initial_state
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command


def test_graph_compiles_with_all_six_approved_nodes():
    graph = build_graph(checkpointer=MemorySaver())

    graph_nodes = set(graph.get_graph().nodes)

    expected_nodes = {
        "agent",
        "tool_executor",
        "result_handler",
        "error_handler",
        "approval_handler",
        "deletion_executor",
    }

    assert expected_nodes.issubset(graph_nodes)





async def test_graph_executes_agent_and_completes(monkeypatch):
    async def fake_agent_node(state):
        return {
            "messages": [
                AIMessage(content="Your tasks are up to date.")
            ],
            "execution_status": "completed",
        }

    monkeypatch.setattr("app.agent.graph.agent_node", fake_agent_node)

    graph = build_graph(checkpointer=MemorySaver())

    state = create_initial_state(
        execution_id="execution-1",
        messages=[HumanMessage(content="Show my tasks")],
    )

    result = await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": "thread-1"}},
    )

    assert result["execution_status"] == "completed"
    assert result["messages"][-1].content == "Your tasks are up to date."




async def test_graph_executes_tool_and_returns_to_agent(monkeypatch):
    agent_calls = []
    execution_order = []

    async def fake_agent_node(state):
        agent_calls.append(state["messages"])

        if len(agent_calls) == 1:
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "list_tasks",
                                "args": {
                                    "status": None,
                                    "priority": None,
                                },
                                "id": "call-list-1",
                                "type": "tool_call",
                            }
                        ],
                    )
                ],
                "execution_status": "running",
            }

        tool_results = [
            message
            for message in state["messages"]
            if isinstance(message, ToolMessage)
        ]

        assert len(tool_results) == 1
        assert tool_results[0].tool_call_id == "call-list-1"

        return {
            "messages": [
                AIMessage(content="You currently have no pending tasks.")
            ],
            "execution_status": "completed",
        }

    async def fake_execute(tool, arguments, config):
        execution_order.append(arguments)
        return {"count": 0, "tasks": []}

    monkeypatch.setattr("app.agent.graph.agent_node", fake_agent_node)
    monkeypatch.setattr(
        tool_executor,
        "TOOLS_BY_NAME",
        {"list_tasks": object()},
    )
    monkeypatch.setattr(
        tool_executor,
        "_execute_regular_tool",
        fake_execute,
    )

    graph = build_graph(checkpointer=MemorySaver())

    state = create_initial_state(
        execution_id="execution-tool-1",
        messages=[HumanMessage(content="Show my tasks")],
    )

    result = await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": "thread-tool-1"}},
    )

    assert len(agent_calls) == 2
    assert len(execution_order) == 1
    assert execution_order[0] == {
        "status": None,
        "priority": None,
    }
    assert result["execution_status"] == "completed"
    assert result["messages"][-1].content == (
        "You currently have no pending tasks."
    )


PENDING_APPROVAL = {
    "approval_id": "approval-graph-1",
    "deletion_request_id": "deletion-graph-1",
    "task_id": "task-1",
    "tool_call_id": "call-delete-1",
}


def install_delete_tool_mock(monkeypatch):
    async def fake_create_request(
        arguments,
        *,
        thread_id,
        execution_id,
        tool_call_id,
    ):
        assert arguments == {"task_id": "task-1"}
        assert thread_id in {"thread-approved", "thread-rejected"}
        assert execution_id in {"execution-approved", "execution-rejected"}
        assert tool_call_id == "call-delete-1"

        return (
            '{"status": "pending_approval"}',
            PENDING_APPROVAL.copy(),
        )

    monkeypatch.setattr(
        tool_executor,
        "TOOLS_BY_NAME",
        {"delete_task": object()},
    )
    monkeypatch.setattr(
        tool_executor,
        "_create_deletion_request",
        fake_create_request,
    )


def make_delete_agent():
    agent_calls = []

    async def fake_agent_node(state):
        agent_calls.append(state["messages"])

        if len(agent_calls) == 1:
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "delete_task",
                                "args": {"task_id": "task-1"},
                                "id": "call-delete-1",
                                "type": "tool_call",
                            }
                        ],
                    )
                ],
                "execution_status": "running",
            }

        tool_results = [
            message
            for message in state["messages"]
            if isinstance(message, ToolMessage)
            and message.tool_call_id == "call-delete-1"
        ]

        assert len(tool_results) == 1

        return {
            "messages": [
                AIMessage(content="The deletion request has been processed.")
            ],
            "execution_status": "completed",
        }

    return fake_agent_node, agent_calls


async def test_graph_resumes_approved_deletion(monkeypatch):
    install_delete_tool_mock(monkeypatch)

    fake_agent, agent_calls = make_delete_agent()
    monkeypatch.setattr(
        "app.agent.graph.agent_node",
        fake_agent,
    )

    deletion_calls = []

    async def fake_deletion_executor(state, config):
        deletion_calls.append(state["pending_approval"])

        return {
            "messages": [
                ToolMessage(
                    id="tool-result:call-delete-1",
                    name="delete_task",
                    tool_call_id="call-delete-1",
                    content="Task task-1 was successfully deleted.",
                )
            ],
            "pending_approval": None,
            "execution_status": "running",
        }

    monkeypatch.setattr(
        "app.agent.graph.deletion_executor_node",
        fake_deletion_executor,
    )

    graph = build_graph(checkpointer=MemorySaver())
    config = {
        "configurable": {"thread_id": "thread-approved"}
    }

    initial_state = create_initial_state(
        execution_id="execution-approved",
        messages=[HumanMessage(content="Delete task task-1")],
    )

    interrupted = await graph.ainvoke(initial_state, config=config)

    assert len(interrupted["__interrupt__"]) == 1
    assert interrupted["__interrupt__"][0].value == {
        "type": "deletion_approval",
        "approval_id": "approval-graph-1",
        "deletion_request_id": "deletion-graph-1",
        "task_id": "task-1",
        "message": "Human approval is required before deleting this task.",
    }

    result = await graph.ainvoke(
        Command(
            resume={
                "approval_id": "approval-graph-1",
                "approved": True,
            }
        ),
        config=config,
    )

    assert len(deletion_calls) == 1
    assert deletion_calls[0] == PENDING_APPROVAL
    assert len(agent_calls) == 2
    assert result["execution_status"] == "completed"
    assert result["pending_approval"] is None
    assert result["messages"][-1].content == (
        "The deletion request has been processed."
    )


async def test_graph_resumes_rejected_deletion_without_execution(monkeypatch):
    install_delete_tool_mock(monkeypatch)

    fake_agent, agent_calls = make_delete_agent()
    monkeypatch.setattr(
        "app.agent.graph.agent_node",
        fake_agent,
    )

    deletion_calls = []

    async def fake_deletion_executor(state, config):
        deletion_calls.append(state)
        raise AssertionError(
            "Deletion executor must not run after rejection."
        )

    monkeypatch.setattr(
        "app.agent.graph.deletion_executor_node",
        fake_deletion_executor,
    )

    graph = build_graph(checkpointer=MemorySaver())
    config = {
        "configurable": {"thread_id": "thread-rejected"}
    }

    initial_state = create_initial_state(
        execution_id="execution-rejected",
        messages=[HumanMessage(content="Delete task task-1")],
    )

    interrupted = await graph.ainvoke(initial_state, config=config)

    assert len(interrupted["__interrupt__"]) == 1

    result = await graph.ainvoke(
        Command(
            resume={
                "approval_id": "approval-graph-1",
                "approved": False,
            }
        ),
        config=config,
    )

    assert deletion_calls == []
    assert len(agent_calls) == 2
    assert result["execution_status"] == "completed"
    assert result["pending_approval"] is None

    rejection = next(
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage)
        and message.tool_call_id == "call-delete-1"
    )

    assert "rejected" in rejection.content.lower()
    assert "not deleted" in rejection.content.lower()
