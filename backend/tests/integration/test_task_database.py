
import pytest
from app.services import TaskService
from app.services.exceptions import TaskNotFoundError


@pytest.mark.asyncio
async def test_task_lifecycle_with_real_database(test_session_factory):
    async with test_session_factory() as session:
        service = TaskService(session)

        # Create
        task = await service.create_task(
            title="Database integration test",
            priority="high",
        )
        task_id = task.id

        # Retrieve
        retrieved = await service.get_task(task_id)
        assert retrieved.title == "Database integration test"

        # Update
        updated = await service.update_task(
            task_id,
            {"title": "Updated integration test"},
        )
        assert updated.title == "Updated integration test"

        # Complete
        completed = await service.complete_task(task_id)
        assert completed.status == "completed"
        assert completed.completed_at is not None

        # Reopen
        reopened = await service.reopen_task(task_id)
        assert reopened.status == "pending"
        assert reopened.completed_at is None

        # Delete
        await service.delete_task(task_id)

        with pytest.raises(TaskNotFoundError):
            await service.get_task(task_id)
