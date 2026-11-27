
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, task: Task) -> Task:
        """Insert a new task into the database."""
        self.session.add(task)

        await self.session.flush()
        await self.session.refresh(task)

        return task

    async def get_by_id(self, task_id: str) -> Task | None:
        """Retrieve a task using its ID."""
        return await self.session.get(Task, task_id)

    
    async def get_all(
        self,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[Task]:
        """Retrieve tasks with optional filters, newest first."""

        statement = select(Task)

        if status is not None:
            statement = statement.where(Task.status == status)

        if priority is not None:
            statement = statement.where(Task.priority == priority)

        statement = statement.order_by(Task.created_at.desc())

        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def update(self, task: Task) -> Task:
        """Persist changes made to an existing task."""
        await self.session.flush()

        return task

    async def delete(self, task: Task) -> None:
        """Delete an existing task."""
        await self.session.delete(task)
        await self.session.flush()
