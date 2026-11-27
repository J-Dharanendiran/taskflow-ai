
import pytest
import pytest_asyncio
from app.database.base import Base
from app.models import Task
from app.repositories import TaskRepository
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture
async def db_session():
    # Create an isolated in-memory SQLite database.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    # Create the tables using our SQLAlchemy models.
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


@pytest.mark.asyncio
async def test_create_task(db_session):
    repository = TaskRepository(db_session)

    task = Task(title="Learn SQLAlchemy")

    created = await repository.create(task)

    assert created.id is not None
    assert created.title == "Learn SQLAlchemy"
    assert created.priority == "medium"
    assert created.status == "pending"
    assert created.created_at is not None
    assert created.updated_at is not None


@pytest.mark.asyncio
async def test_get_by_id(db_session):
    repository = TaskRepository(db_session)

    task = Task(title="Build TaskFlow")
    await repository.create(task)

    retrieved = await repository.get_by_id(task.id)

    assert retrieved is not None
    assert retrieved.id == task.id
    assert retrieved.title == "Build TaskFlow"


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_missing_task(db_session):
    repository = TaskRepository(db_session)

    result = await repository.get_by_id("non-existent-id")

    assert result is None


@pytest.mark.asyncio
async def test_get_all(db_session):
    repository = TaskRepository(db_session)

    await repository.create(Task(title="Task One"))
    await repository.create(Task(title="Task Two"))

    tasks = await repository.get_all()

    assert len(tasks) == 2
    assert {task.title for task in tasks} == {
        "Task One",
        "Task Two",
    }


@pytest.mark.asyncio
async def test_update_task(db_session):
    repository = TaskRepository(db_session)

    task = Task(title="Original title")
    await repository.create(task)

    task.title = "Updated title"
    task.priority = "high"

    updated = await repository.update(task)

    assert updated.title == "Updated title"
    assert updated.priority == "high"


@pytest.mark.asyncio
async def test_delete_task(db_session):
    repository = TaskRepository(db_session)

    task = Task(title="Task to delete")
    await repository.create(task)

    await repository.delete(task)

    result = await repository.get_by_id(task.id)

    assert result is None


@pytest.mark.asyncio
async def test_rollback_discards_uncommitted_task(db_session):
    repository = TaskRepository(db_session)

    task = Task(title="Temporary task")
    await repository.create(task)

    task_id = task.id

    await db_session.rollback()

    result = await repository.get_by_id(task_id)

    assert result is None


@pytest.mark.asyncio
async def test_database_rejects_empty_title(db_session):
    repository = TaskRepository(db_session)

    task = Task(title="   ")

    with pytest.raises(IntegrityError):
        await repository.create(task)

    await db_session.rollback()


@pytest.mark.asyncio
async def test_database_rejects_invalid_priority(db_session):
    repository = TaskRepository(db_session)

    task = Task(
        title="Invalid priority task",
        priority="urgent",
    )

    with pytest.raises(IntegrityError):
        await repository.create(task)

    await db_session.rollback()


@pytest.mark.asyncio
async def test_created_timestamp_is_timezone_aware_utc(db_session):
    task = Task(title="Test UTC timestamp")

    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    assert task.created_at.tzinfo is not None
    assert task.created_at.utcoffset().total_seconds() == 0


@pytest.mark.asyncio
async def test_updated_timestamp_is_timezone_aware_utc(db_session):
    task = Task(title="Test UTC update")
    
    db_session.add(task)
    await db_session.commit()

    task.title = "Updated UTC task"
    await db_session.commit()
    await db_session.refresh(task)

    assert task.updated_at.tzinfo is not None
    assert task.updated_at.utcoffset().total_seconds() == 0


@pytest.mark.asyncio
async def test_get_all_filters_by_status(db_session):
    repository = TaskRepository(db_session)

    await repository.create(Task(title="Pending task", status="pending"))
    await repository.create(Task(title="Completed task", status="completed"))

    tasks = await repository.get_all(status="pending")

    assert len(tasks) == 1
    assert tasks[0].title == "Pending task"


@pytest.mark.asyncio
async def test_get_all_filters_by_priority(db_session):
    repository = TaskRepository(db_session)

    await repository.create(Task(title="High task", priority="high"))
    await repository.create(Task(title="Low task", priority="low"))

    tasks = await repository.get_all(priority="high")

    assert len(tasks) == 1
    assert tasks[0].title == "High task"


@pytest.mark.asyncio
async def test_get_all_filters_by_status_and_priority(db_session):
    repository = TaskRepository(db_session)

    await repository.create(
        Task(title="Matching task", status="pending", priority="high")
    )
    await repository.create(
        Task(title="Wrong status", status="completed", priority="high")
    )
    await repository.create(
        Task(title="Wrong priority", status="pending", priority="low")
    )

    tasks = await repository.get_all(
        status="pending",
        priority="high",
    )

    assert len(tasks) == 1
    assert tasks[0].title == "Matching task"


@pytest.mark.asyncio
async def test_get_all_returns_empty_list_when_no_tasks_match(db_session):
    repository = TaskRepository(db_session)

    await repository.create(
        Task(title="Low priority task", priority="low")
    )

    tasks = await repository.get_all(
        status="completed",
        priority="high",
    )

    assert tasks == []
