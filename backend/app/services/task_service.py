
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task
from app.repositories import TaskRepository
from app.services.exceptions import (
    InvalidTaskDataError,
    TaskNotFoundError,
)


class TaskService:
    VALID_PRIORITIES = {"low", "medium", "high"}

    VALID_STATUSES = {
        "pending",
        "in_progress",
        "completed",
    }

    ALLOWED_UPDATE_FIELDS = {
        "title",
        "description",
        "due_date",
        "priority",
    }

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = TaskRepository(session)

    # -------------------------
    # Validation
    # -------------------------

    def _validate_title(self, title: str) -> None:
        if not isinstance(title, str) or not title.strip():
            raise InvalidTaskDataError(
                "Task title cannot be empty."
            )

        if len(title) > 255:
            raise InvalidTaskDataError(
                "Task title cannot exceed 255 characters."
            )

    def _validate_priority(self, priority: str) -> None:
        if (
            not isinstance(priority, str)
            or priority not in self.VALID_PRIORITIES
        ):
            raise InvalidTaskDataError(
                "Priority must be low, medium, or high."
            )

    def _validate_status(self, status: str) -> None:
        if (
            not isinstance(status, str)
            or status not in self.VALID_STATUSES
        ):
            raise InvalidTaskDataError(
                "Status must be pending, in_progress, or completed."
            )

    def _validate_due_date(self, due_date: date | None) -> None:
        if due_date is not None and type(due_date) is not date:
            raise InvalidTaskDataError(
                "Due date must be a date or None."
            )

    def _validate_updates(self, updates: dict) -> None:
        if not isinstance(updates, dict):
            raise InvalidTaskDataError(
                "Updates must be provided as a dictionary."
            )

        unknown_fields = set(updates) - self.ALLOWED_UPDATE_FIELDS

        if unknown_fields:
            raise InvalidTaskDataError(
                f"Fields cannot be updated: {', '.join(sorted(unknown_fields))}"
            )

        if "title" in updates:
            self._validate_title(updates["title"])

        if "priority" in updates:
            self._validate_priority(updates["priority"])

        if "due_date" in updates:
            self._validate_due_date(updates["due_date"])

        if "description" in updates:
            description = updates["description"]

            if description is not None and not isinstance(description, str):
                raise InvalidTaskDataError(
                    "Description must be a string or None."
                )

    # -------------------------
    # Task creation
    # -------------------------

    async def create_task(
        self,
        title: str,
        description: str | None = None,
        due_date: date | None = None,
        priority: str = "medium",
    ) -> Task:
        self._validate_title(title)
        self._validate_priority(priority)
        self._validate_due_date(due_date)

        if description is not None and not isinstance(description, str):
            raise InvalidTaskDataError(
                "Description must be a string or None."
            )

        task = Task(
            title=title,
            description=description,
            due_date=due_date,
            priority=priority,
        )

        try:
            created = await self.repository.create(task)
            await self.session.commit()
            return created
        except Exception:
            await self.session.rollback()
            raise

    # -------------------------
    # Task retrieval
    # -------------------------

    async def get_task(self, task_id: str) -> Task:
        task = await self.repository.get_by_id(task_id)

        if task is None:
            raise TaskNotFoundError(
                f"Task '{task_id}' was not found."
            )

        return task

    async def list_tasks(
        self,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[Task]:
        """Retrieve tasks with optional status and priority filters."""

        if status is not None:
            self._validate_status(status)

        if priority is not None:
            self._validate_priority(priority)

        return await self.repository.get_all(
            status=status,
            priority=priority,
        )

    # -------------------------
    # Task updates
    # -------------------------

    async def update_task(
        self,
        task_id: str,
        updates: dict,
    ) -> Task:
        self._validate_updates(updates)

        try:
            task = await self.get_task(task_id)

            for field, value in updates.items():
                setattr(task, field, value)

            updated = await self.repository.update(task)
            await self.session.commit()

            return updated

        except Exception:
            await self.session.rollback()
            raise

    # -------------------------
    # Task completion
    # -------------------------

    async def complete_task(self, task_id: str) -> Task:
        try:
            task = await self.get_task(task_id)

            if task.status != "completed":
                task.status = "completed"
                task.completed_at = datetime.now(UTC)

            updated = await self.repository.update(task)
            await self.session.commit()

            return updated

        except Exception:
            await self.session.rollback()
            raise

    # -------------------------
    # Task reopening
    # -------------------------

    async def reopen_task(self, task_id: str) -> Task:
        try:
            task = await self.get_task(task_id)

            task.status = "pending"
            task.completed_at = None

            updated = await self.repository.update(task)
            await self.session.commit()

            return updated

        except Exception:
            await self.session.rollback()
            raise

    # -------------------------
    # Task deletion
    # -------------------------

    async def delete_task(self, task_id: str, *, commit: bool = True) -> None:
        """Delete a task, optionally leaving commit control to the caller.

        The approval-gated executor uses ``commit=False`` so the task deletion,
        deletion-request outcome, and execution ledger share one transaction.
        Existing callers retain the original commit-on-success behavior.
        """
        try:
            task = await self.get_task(task_id)
            await self.repository.delete(task)
            if commit:
                await self.session.commit()
        except Exception:
            if commit:
                await self.session.rollback()
            raise
