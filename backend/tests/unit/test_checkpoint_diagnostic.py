import pytest
from app.agent.graph import build_graph
from app.agent.state import create_initial_state
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver


@pytest.mark.asyncio
async def test_inspect_approval_checkpoint(monkeypatch):
    async def fake_agent_node(state):
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

    async def fake_tool_executor_node(state, config):
        return {
            "messages": [
                ToolMessage(
                    id="tool-result:call-delete-1",
                    name="delete_task",
                    tool_call_id="call-delete-1",
                    content='{"status": "pending_approval"}',
                )
            ],
            "pending_approval": {
                "approval_id": "approval-test",
                "deletion_request_id": "deletion-test",
                "task_id": "task-1",
                "tool_call_id": "call-delete-1",
            },
            "execution_status": "waiting_for_approval",
        }

    monkeypatch.setattr("app.agent.graph.agent_node", fake_agent_node)
    monkeypatch.setattr(
        "app.agent.graph.tool_executor_node",
        fake_tool_executor_node,
    )

    graph = build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "thread-diagnostic"}}

    await graph.ainvoke(
        create_initial_state(
            execution_id="execution-diagnostic",
            messages=[HumanMessage(content="Delete task task-1")],
        ),
        config=config,
    )

    snapshot = await graph.aget_state(config)

    print("SNAPSHOT STATUS:", snapshot.values.get("execution_status"))
    print("TOP-LEVEL INTERRUPTS:", snapshot.interrupts)
    print("TASKS:", snapshot.tasks)
    print("TASK INTERRUPTS:", [task.interrupts for task in snapshot.tasks])

    assert snapshot.interrupts