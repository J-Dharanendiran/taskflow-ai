"""
Generate a Mermaid source file and PNG visualization of the compiled TaskFlow AI graph.

Run this script from the backend directory:
    uv run python visualize_graph.py

Outputs:
    taskflow_graph.mmd
    taskflow_graph.png

The script uses the real compiled graph from app.agent.graph, not a manually
drawn approximation.
"""

import asyncio
from pathlib import Path

from langchain_core.runnables.graph import MermaidDrawMethod
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy.engine import make_url

from app.agent.graph import build_graph
from app.core.config import settings


def get_sqlite_path(database_url: str) -> str:
    """Convert the application's SQLAlchemy SQLite URL to a file path."""
    url = make_url(database_url)

    if not url.drivername.startswith("sqlite"):
        raise ValueError(
            "TaskFlow's graph visualizer expects a SQLite database URL; "
            f"received driver {url.drivername!r}."
        )

    database = url.database
    if not database:
        raise ValueError("The configured SQLite database URL has no database path.")

    # AsyncSqliteSaver expects a SQLite path, not a SQLAlchemy URL.
    return database


async def main() -> None:
    database_path = get_sqlite_path(settings.database_url)
    output_dir = Path(__file__).resolve().parent

    mermaid_path = output_dir / "taskflow_graph.mmd"
    png_path = output_dir / "taskflow_graph.png"

    async with AsyncSqliteSaver.from_conn_string(database_path) as checkpointer:
        await checkpointer.setup()
        graph = build_graph(checkpointer)

        graph_view = graph.get_graph()
        mermaid_source = graph_view.draw_mermaid()

        mermaid_path.write_text(mermaid_source, encoding="utf-8")
        print(f"Mermaid source saved to: {mermaid_path}")

        try:
            png_bytes = graph_view.draw_mermaid_png(
                draw_method=MermaidDrawMethod.API
            )
        except Exception as exc:
            raise RuntimeError(
                "The Mermaid source was generated, but PNG rendering failed. "
                "Check your internet connection and Mermaid rendering dependencies. "
                f"Mermaid source is available at: {mermaid_path}"
            ) from exc

        png_path.write_bytes(png_bytes)
        print(f"PNG visualization saved to: {png_path}")


if __name__ == "__main__":
    asyncio.run(main())
