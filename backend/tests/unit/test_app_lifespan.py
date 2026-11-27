
from pathlib import Path

from app.core.config import settings
from app.main import app, lifespan


async def test_lifespan_initializes_checkpointer_and_graph(
    monkeypatch, tmp_path: Path
):
    database_path = tmp_path / "test_taskflow.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    monkeypatch.setattr(settings, "database_url", database_url)

    async with lifespan(app):
        assert hasattr(app.state, "checkpointer")
        assert hasattr(app.state, "graph")

        graph_nodes = set(app.state.graph.get_graph().nodes)

        expected_nodes = {
            "agent",
            "tool_executor",
            "result_handler",
            "error_handler",
            "approval_handler",
            "deletion_executor",
        }

        assert expected_nodes.issubset(graph_nodes)

    assert database_path.exists()
