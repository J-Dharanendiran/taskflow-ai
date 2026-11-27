from unittest.mock import AsyncMock

import app.agent.nodes as agent_nodes
import pytest
from app.agent.state import create_initial_state
from langchain_core.messages import AIMessage, HumanMessage


class FakeChatModel:
    def __init__(self, response):
        self.response = response
        self.ainvoke = AsyncMock(return_value=response)

    def bind_tools(self, tools):
        self.tools = tools
        return self


@pytest.fixture
def initial_state():
    return create_initial_state(
        execution_id="execution-1",
        messages=[
            HumanMessage(
                id="message-1",
                content="Help me with my tasks.",
            )
        ],
    )


@pytest.fixture
def config():
    return {"configurable": {"thread_id": "thread-1"}}


@pytest.mark.asyncio
async def test_agent_routes_tool_calls(
    monkeypatch,
    initial_state,
    config,
):
    response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "list_tasks",
                "args": {},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )
    model = FakeChatModel(response)
    monkeypatch.setattr(agent_nodes, "create_chat_model", lambda: model)

    result = await agent_nodes.agent_node(initial_state, config)

    assert result["messages"] == [response]
    assert result["iteration_count"] == 1
    assert "execution_status" not in result
    model.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_returns_pending_clarification(
    monkeypatch,
    initial_state,
    config,
):
    response = AIMessage(
        content=(
            '<taskflow_clarification>'
            '{"reason":"missing_information",'
            '"question":"What is the task title?"}'
            '</taskflow_clarification>'
        )
    )
    model = FakeChatModel(response)
    monkeypatch.setattr(agent_nodes, "create_chat_model", lambda: model)

    result = await agent_nodes.agent_node(initial_state, config)

    assert result["execution_status"] == "waiting_for_clarification"
    assert result["pending_clarification"] == {
        "question": "What is the task title?",
        "reason": "missing_information",
        "original_message_id": "message-1",
    }
    assert result["messages"][0].content == "What is the task title?"
    assert result["iteration_count"] == 1


@pytest.mark.asyncio
async def test_agent_returns_unsupported_request(
    monkeypatch,
    initial_state,
    config,
):
    response = AIMessage(
        content=(
            "<taskflow_unsupported>"
            "I cannot access your email account."
            "</taskflow_unsupported>"
        )
    )
    model = FakeChatModel(response)
    monkeypatch.setattr(agent_nodes, "create_chat_model", lambda: model)

    result = await agent_nodes.agent_node(initial_state, config)

    assert result["execution_status"] == "completed"
    assert result["messages"][0].content == (
        "I cannot access your email account."
    )
    assert "pending_clarification" not in result
    assert "pending_approval" not in result
    assert result["iteration_count"] == 1


@pytest.mark.asyncio
async def test_agent_returns_normal_final_response(
    monkeypatch,
    initial_state,
    config,
):
    response = AIMessage(content="Hello! How can I help you?")
    model = FakeChatModel(response)
    monkeypatch.setattr(agent_nodes, "create_chat_model", lambda: model)

    result = await agent_nodes.agent_node(initial_state, config)

    assert result["execution_status"] == "completed"
    assert result["messages"] == [response]
    assert result["iteration_count"] == 1
    assert "pending_clarification" not in result
    assert "pending_approval" not in result


@pytest.mark.asyncio
async def test_agent_rejects_invalid_clarification_reason(
    monkeypatch,
    initial_state,
    config,
):
    response = AIMessage(
        content=(
            '<taskflow_clarification>'
            '{"reason":"unknown_reason","question":"What do you mean?"}'
            '</taskflow_clarification>'
        )
    )
    model = FakeChatModel(response)
    monkeypatch.setattr(agent_nodes, "create_chat_model", lambda: model)

    with pytest.raises(ValueError, match="Invalid clarification reason"):
        await agent_nodes.agent_node(initial_state, config)


@pytest.mark.asyncio
async def test_agent_stops_at_iteration_limit(
    monkeypatch,
    initial_state,
    config,
):
    initial_state["iteration_count"] = agent_nodes.MAX_AGENT_ITERATIONS

    model = FakeChatModel(AIMessage(content="This should not be called."))
    monkeypatch.setattr(agent_nodes, "create_chat_model", lambda: model)

    result = await agent_nodes.agent_node(initial_state, config)

    assert result["execution_status"] == "completed"
    assert "iteration_count" not in result
    assert initial_state["iteration_count"] == agent_nodes.MAX_AGENT_ITERATIONS
    model.ainvoke.assert_not_awaited()

@pytest.mark.asyncio
async def test_agent_counts_failed_llm_invocation(
    monkeypatch,
    initial_state,
):
    fake_model = FakeChatModel(AIMessage(content="unused"))
    fake_model.ainvoke.side_effect = TimeoutError("LLM request timed out")

    monkeypatch.setattr(
        agent_nodes,
        "create_chat_model",
        lambda: fake_model,
    )

    result = await agent_nodes.agent_node(
        initial_state,
        {"configurable": {"thread_id": "thread-1"}},
    )

    assert result["iteration_count"] == 1
    assert result["execution_status"] == "failed"
    assert "couldn't process your request" in result["messages"][0].content
    fake_model.ainvoke.assert_awaited_once()