
import json

import app.tools.task_tools as task_tools
import pytest
import pytest_asyncio
from app.database.base import Base
from app.services.exceptions import TaskNotFoundError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture
async def tool_session_factory(monkeypatch):
    """Provide an isolated SQLite database for tool tests."""

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    monkeypatch.setattr(
        task_tools,
        "AsyncSessionLocal",
        session_factory,
    )

    yield session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_task_changes_title_without_altering_other_fields(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Original task",
            "description": "Keep this description",
            "due_date": "2026-12-01",
            "priority": "medium",
        })
    )

    task_id = created["task"]["id"]

    updated = json.loads(
        await task_tools.update_task.ainvoke({
            "task_id": task_id,
            "updates": {
                "title": "Updated task",
            },
        })
    )

    task = updated["task"]

    assert task["title"] == "Updated task"
    assert task["description"] == "Keep this description"
    assert task["due_date"] == "2026-12-01"
    assert task["priority"] == "medium"


@pytest.mark.asyncio
async def test_update_task_explicitly_clears_description(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Task with description",
            "description": "Remove this description",
        })
    )

    task_id = created["task"]["id"]

    updated = json.loads(
        await task_tools.update_task.ainvoke({
            "task_id": task_id,
            "updates": {
                "description": None,
            },
        })
    )

    task = updated["task"]

    assert task["description"] is None
    assert task["title"] == "Task with description"


@pytest.mark.asyncio
async def test_update_task_changes_priority(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Priority test",
            "priority": "low",
        })
    )

    task_id = created["task"]["id"]

    updated = json.loads(
        await task_tools.update_task.ainvoke({
            "task_id": task_id,
            "updates": {
                "priority": "high",
            },
        })
    )

    assert updated["task"]["priority"] == "high"


@pytest.mark.asyncio
async def test_update_task_rejects_empty_updates():
    with pytest.raises(ValidationError):
        await task_tools.update_task.ainvoke({
            "task_id": "123",
            "updates": {},
        })


@pytest.mark.asyncio
async def test_update_task_rejects_invalid_priority(
    tool_session_factory,
):
    with pytest.raises(ValidationError):
        await task_tools.update_task.ainvoke({
            "task_id": "123",
            "updates": {
                "priority": "urgent",
            },
        })


@pytest.mark.asyncio
async def test_update_task_rejects_nonexistent_task(
    tool_session_factory,
):
    with pytest.raises(TaskNotFoundError):
        await task_tools.update_task.ainvoke({
            "task_id": "00000000-0000-0000-0000-000000000000",
            "updates": {
                "title": "Should not exist",
            },
        })


# -------------------------------------------------------------------
# Create task tool tests
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_task_with_defaults(tool_session_factory):
    result = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Default task",
        })
    )

    assert result["success"] is True
    assert result["task"]["title"] == "Default task"
    assert result["task"]["priority"] == "medium"
    assert result["task"]["status"] == "pending"
    assert result["task"]["description"] is None
    assert result["task"]["due_date"] is None


@pytest.mark.asyncio
async def test_create_task_with_custom_values(tool_session_factory):
    result = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Custom task",
            "description": "Task description",
            "due_date": "2026-12-15",
            "priority": "high",
        })
    )

    task = result["task"]

    assert result["success"] is True
    assert task["title"] == "Custom task"
    assert task["description"] == "Task description"
    assert task["due_date"] == "2026-12-15"
    assert task["priority"] == "high"


@pytest.mark.asyncio
async def test_create_task_rejects_invalid_title():
    with pytest.raises(ValidationError):
        await task_tools.create_task.ainvoke({
            "title": "   ",
        })


# -------------------------------------------------------------------
# List tasks tool tests
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tasks_returns_all_tasks(tool_session_factory):
    await task_tools.create_task.ainvoke({
        "title": "First task",
        "priority": "high",
    })

    await task_tools.create_task.ainvoke({
        "title": "Second task",
        "priority": "low",
    })

    result = json.loads(
        await task_tools.list_tasks.ainvoke({})
    )

    assert result["success"] is True
    assert result["count"] == 2
    assert len(result["tasks"]) == 2


@pytest.mark.asyncio
async def test_list_tasks_filters_by_priority(tool_session_factory):
    await task_tools.create_task.ainvoke({
        "title": "High priority task",
        "priority": "high",
    })

    await task_tools.create_task.ainvoke({
        "title": "Low priority task",
        "priority": "low",
    })

    result = json.loads(
        await task_tools.list_tasks.ainvoke({
            "priority": "high",
        })
    )

    assert result["count"] == 1
    assert result["tasks"][0]["title"] == "High priority task"
    assert result["tasks"][0]["priority"] == "high"


@pytest.mark.asyncio
async def test_list_tasks_returns_empty_result_when_no_tasks_match(
    tool_session_factory,
):
    await task_tools.create_task.ainvoke({
        "title": "Pending task",
    })

    result = json.loads(
        await task_tools.list_tasks.ainvoke({
            "status": "completed",
        })
    )

    assert result["success"] is True
    assert result["count"] == 0
    assert result["tasks"] == []


# -------------------------------------------------------------------
# Delete task tool tests
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_task_requests_approval_without_deleting(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Task awaiting deletion",
            "description": "This task must remain until approval.",
        })
    )

    task_id = created["task"]["id"]

    result = json.loads(
        await task_tools.delete_task.ainvoke({
            "task_id": task_id,
        })
    )

    assert result["success"] is True
    assert result["task_id"] == task_id
    assert result["status"] == "pending_approval"
    assert result["task"]["title"] == "Task awaiting deletion"

    # A deletion request must not delete the actual task.
    remaining = json.loads(
        await task_tools.list_tasks.ainvoke({})
    )

    assert remaining["count"] == 1
    assert remaining["tasks"][0]["id"] == task_id


@pytest.mark.asyncio
async def test_delete_task_rejects_nonexistent_task(
    tool_session_factory,
):
    with pytest.raises(TaskNotFoundError):
        await task_tools.delete_task.ainvoke({
            "task_id": "00000000-0000-0000-0000-000000000000",
        })


# -------------------------------------------------------------------
# Complete task tool tests
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_task_sets_completed_status_and_timestamp(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Task to complete",
        })
    )

    task_id = created["task"]["id"]

    result = json.loads(
        await task_tools.complete_task.ainvoke({
            "task_id": task_id,
        })
    )

    task = result["task"]

    assert result["success"] is True
    assert task["id"] == task_id
    assert task["status"] == "completed"
    assert task["completed_at"] is not None


@pytest.mark.asyncio
async def test_complete_task_rejects_nonexistent_task(
    tool_session_factory,
):
    with pytest.raises(TaskNotFoundError):
        await task_tools.complete_task.ainvoke({
            "task_id": "00000000-0000-0000-0000-000000000000",
        })


# -------------------------------------------------------------------
# Reopen task tool tests
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reopen_task_resets_status_and_completion_timestamp(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Task to reopen",
        })
    )

    task_id = created["task"]["id"]

    await task_tools.complete_task.ainvoke({
        "task_id": task_id,
    })

    result = json.loads(
        await task_tools.reopen_task.ainvoke({
            "task_id": task_id,
        })
    )

    task = result["task"]

    assert result["success"] is True
    assert task["id"] == task_id
    assert task["status"] == "pending"
    assert task["completed_at"] is None


@pytest.mark.asyncio
async def test_reopen_task_rejects_nonexistent_task(
    tool_session_factory,
):
    with pytest.raises(TaskNotFoundError):
        await task_tools.reopen_task.ainvoke({
            "task_id": "00000000-0000-0000-0000-000000000000",
        })
