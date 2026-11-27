
"""Unified LangGraph workflow for TaskFlow AI."""

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.approval_handler import approval_handler_node
from app.agent.deletion_executor import deletion_executor_node
from app.agent.error_handler import error_handler_node
from app.agent.nodes import agent_node
from app.agent.result_handler import result_handler_node
from app.agent.routing import (
    route_after_agent,
    route_after_approval_handler,
    route_after_result_handler,
)
from app.agent.state import AgentState
from app.agent.tool_executor import tool_executor_node


def build_graph(checkpointer: Any):
    """Build and compile the unified TaskFlow AI workflow.

    A persistent checkpointer must be supplied by the application.
    """

    workflow = StateGraph(AgentState)

    # Register the six approved logical nodes.
    workflow.add_node("agent", agent_node)
    workflow.add_node("tool_executor", tool_executor_node)
    workflow.add_node("result_handler", result_handler_node)
    workflow.add_node("error_handler", error_handler_node)
    workflow.add_node("approval_handler", approval_handler_node)
    workflow.add_node("deletion_executor", deletion_executor_node)

    # Entry point.
    workflow.add_edge(START, "agent")

    # Agent routing.
    workflow.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tool_executor": "tool_executor",
            END: END,
        },
    )

    # Tool execution and result validation.
    workflow.add_edge("tool_executor", "result_handler")

    workflow.add_conditional_edges(
        "result_handler",
        route_after_result_handler,
        {
            "approval_handler": "approval_handler",
            "error_handler": "error_handler",
            "agent": "agent",
        },
    )

    # Approval handling.
    workflow.add_conditional_edges(
        "approval_handler",
        route_after_approval_handler,
        {
            "deletion_executor": "deletion_executor",
            "agent": "agent",
        },
    )

    # Approved deletion returns through result validation.
    workflow.add_edge("deletion_executor", "result_handler")

    # Tool errors return to the Agent for an accurate response.
    workflow.add_edge("error_handler", "agent")

    return workflow.compile(checkpointer=checkpointer)
