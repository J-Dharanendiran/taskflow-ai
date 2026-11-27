"""TaskFlow AI LangGraph orchestration package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.state import AgentState

__all__ = ["AgentState"]


def __getattr__(name: str):
    if name == "AgentState":
        from app.agent.state import AgentState

        return AgentState
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
