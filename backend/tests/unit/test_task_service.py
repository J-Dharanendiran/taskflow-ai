
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.database.base import Base
from app.services import TaskService
from app.services.exceptions import InvalidTaskDataError, TaskNotFoundError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with SessionLocal() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def task_service(db_session):
    return TaskService(db_session)


@pytest.mark.asyncio
async def test_create_task_with_defaults(task_service):
    task = await task_service.create_task(
        title="Learn Python"
    )

    assert task.id is not None
    assert task.title == "Learn Python"
    assert task.priority == "medium"
    assert task.status == "pending"
    assert task.description is None
    assert task.due_date is None
    assert task.completed_at is None
    assert task.created_at is not None
    assert task.updated_at is not None


@pytest.mark.asyncio
async def test_create_task_with_custom_values(task_service):
    from datetime import date

    task = await task_service.create_task(
        title="Build TaskFlow",
        description="Develop the backend",
        due_date=date(2026, 12, 1),
        priority="high",
    )

    assert task.title == "Build TaskFlow"
    assert task.description == "Develop the backend"
    assert task.due_date == date(2026, 12, 1)
    assert task.priority == "high"


@pytest.mark.asyncio
@pytest.mark.parametrize("title", ["", "   ", "\t", "\n"])
async def test_create_task_rejects_empty_title(task_service, title):
    with pytest.raises(InvalidTaskDataError):
        await task_service.create_task(title=title)


@pytest.mark.asyncio
async def test_create_task_rejects_oversized_title(task_service):
    with pytest.raises(InvalidTaskDataError):
        await task_service.create_task(
            title="A" * 256
        )


@pytest.mark.asyncio
async def test_create_task_rejects_invalid_priority(task_service):
    with pytest.raises(InvalidTaskDataError):
        await task_service.create_task(
            title="Learn Python",
            priority="urgent",
        )


@pytest.mark.asyncio
async def test_get_task(task_service):
    created = await task_service.create_task("Learn Python")

    retrieved = await task_service.get_task(created.id)

    assert retrieved.id == created.id
    assert retrieved.title == "Learn Python"


@pytest.mark.asyncio
async def test_get_task_rejects_missing_id(task_service):
    with pytest.raises(TaskNotFoundError):
        await task_service.get_task("non-existent-id")


@pytest.mark.asyncio
async def test_list_tasks(task_service):
    await task_service.create_task("Task One")
    await task_service.create_task("Task Two")

    tasks = await task_service.list_tasks()

    assert len(tasks) == 2
    assert {task.title for task in tasks} == {
        "Task One",
        "Task Two",
    }


@pytest.mark.asyncio
async def test_update_task(task_service):
    task = await task_service.create_task("Original title")

    updated = await task_service.update_task(
        task.id,
        {
            "title": "Updated title",
            "priority": "high",
        },
    )

    assert updated.title == "Updated title"
    assert updated.priority == "high"


@pytest.mark.asyncio
async def test_update_task_rejects_invalid_fields(task_service):
    task = await task_service.create_task("Learn Python")

    with pytest.raises(InvalidTaskDataError):
        await task_service.update_task(
            task.id,
            {"status": "completed"},
        )


@pytest.mark.asyncio
async def test_complete_task(task_service):
    task = await task_service.create_task("Finish project")

    completed = await task_service.complete_task(task.id)

    assert completed.status == "completed"
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_reopen_task(task_service):
    task = await task_service.create_task("Finish project")

    await task_service.complete_task(task.id)

    reopened = await task_service.reopen_task(task.id)

    assert reopened.status == "pending"
    assert reopened.completed_at is None


@pytest.mark.asyncio
async def test_delete_task(task_service):
    task = await task_service.create_task("Task to delete")

    await task_service.delete_task(task.id)

    with pytest.raises(TaskNotFoundError):
        await task_service.get_task(task.id)


@pytest.mark.asyncio
async def test_update_task_refreshes_updated_at(task_service):
    task = await task_service.create_task("Learn Python")

    # Set an old timestamp so the change is unambiguous.
    task.updated_at = datetime(2020, 1, 1, tzinfo=UTC)
    await task_service.session.commit()

    updated = await task_service.update_task(
        task.id,
        {"title": "Learn Advanced Python"},
    )

    assert updated.updated_at.year > 2020


@pytest.mark.asyncio
async def test_completing_task_twice_preserves_original_timestamp(task_service):
    task = await task_service.create_task("Finish project")

    first_completion = await task_service.complete_task(task.id)
    original_timestamp = first_completion.completed_at

    second_completion = await task_service.complete_task(task.id)

    assert second_completion.status == "completed"
    assert second_completion.completed_at == original_timestamp


@pytest.mark.asyncio
async def test_reopening_task_clears_completion_timestamp(task_service):
    task = await task_service.create_task("Finish project")

    completed = await task_service.complete_task(task.id)
    assert completed.completed_at is not None

    reopened = await task_service.reopen_task(task.id)

    assert reopened.status == "pending"
    assert reopened.completed_at is None
    assert reopened.updated_at is not None


@pytest.mark.asyncio
async def test_create_task_rolls_back_when_commit_fails(
    task_service,
    monkeypatch,
):
    async def fail_commit():
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(
        task_service.session,
        "commit",
        fail_commit,
    )

    with pytest.raises(RuntimeError, match="Simulated database failure"):
        await task_service.create_task("Temporary task")

    tasks = await task_service.list_tasks()

    assert tasks == []



@pytest.mark.asyncio
async def test_update_task_rolls_back_when_commit_fails(
    task_service,
    monkeypatch,
):
    task = await task_service.create_task("Original title")

    # Capture the ID before rollback expires ORM objects.
    task_id = task.id

    async def fail_commit():
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(
        task_service.session,
        "commit",
        fail_commit,
    )

    with pytest.raises(RuntimeError, match="Simulated database failure"):
        await task_service.update_task(
            task_id,
            {"title": "Changed title"},
        )

    retrieved = await task_service.get_task(task_id)

    assert retrieved.title == "Original title"


@pytest.mark.asyncio
async def test_create_task_rejects_datetime_as_due_date(task_service):
    from datetime import datetime

    with pytest.raises(InvalidTaskDataError):
        await task_service.create_task(
            title="Learn Python",
            due_date=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_update_task_rejects_datetime_as_due_date(task_service):
    from datetime import datetime

    task = await task_service.create_task("Learn Python")

    with pytest.raises(InvalidTaskDataError):
        await task_service.update_task(
            task.id,
            {"due_date": datetime.now(UTC)},
        )


@pytest.mark.asyncio
async def test_list_tasks_filters_by_status(task_service):
    pending = await task_service.create_task("Pending task")
    completed = await task_service.create_task("Completed task")

    await task_service.complete_task(completed.id)

    tasks = await task_service.list_tasks(status="pending")

    assert len(tasks) == 1
    assert tasks[0].id == pending.id


@pytest.mark.asyncio
async def test_list_tasks_filters_by_priority(task_service):
    await task_service.create_task(
        "High priority task",
        priority="high",
    )
    await task_service.create_task(
        "Low priority task",
        priority="low",
    )

    tasks = await task_service.list_tasks(priority="high")

    assert len(tasks) == 1
    assert tasks[0].title == "High priority task"


@pytest.mark.asyncio
async def test_list_tasks_filters_by_status_and_priority(task_service):
    matching = await task_service.create_task(
        "Matching task",
        priority="high",
    )

    completed = await task_service.create_task(
        "Completed high priority task",
        priority="high",
    )
    await task_service.complete_task(completed.id)

    await task_service.create_task(
        "Low priority pending task",
        priority="low",
    )

    tasks = await task_service.list_tasks(
        status="pending",
        priority="high",
    )

    assert len(tasks) == 1
    assert tasks[0].id == matching.id


@pytest.mark.asyncio
async def test_list_tasks_returns_empty_list_when_no_tasks_match(task_service):
    await task_service.create_task(
        "Low priority task",
        priority="low",
    )

    tasks = await task_service.list_tasks(
        status="completed",
        priority="high",
    )

    assert tasks == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    ["invalid", "cancelled", "", "PENDING"],
)
async def test_list_tasks_rejects_invalid_status(task_service, status):
    with pytest.raises(InvalidTaskDataError):
        await task_service.list_tasks(status=status)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "priority",
    ["urgent", "critical", "", "HIGH"],
)
async def test_list_tasks_rejects_invalid_priority(task_service, priority):
    with pytest.raises(InvalidTaskDataError):
        await task_service.list_tasks(priority=priority)

