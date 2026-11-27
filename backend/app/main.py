from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy.engine import make_url

from app.agent.graph import build_graph
from app.api.v1.router import api_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = make_url(settings.database_url)

    if database_url.get_backend_name() != "sqlite":
        raise RuntimeError(
            "TaskFlow AI currently requires SQLite for application persistence."
        )

    database_path = database_url.database

    if not database_path or database_path == ":memory:":
        raise RuntimeError(
            "A file-backed SQLite database is required for shared persistence."
        )

    Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    async with AsyncSqliteSaver.from_conn_string(database_path) as checkpointer:
        await checkpointer.setup()

        app.state.checkpointer = checkpointer
        app.state.graph = build_graph(checkpointer)

        yield


app = FastAPI(
    title=settings.app_name,
    description="AI-powered task management application",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(
    api_router,
    prefix=settings.api_v1_prefix,
)