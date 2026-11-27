
from datetime import date

from langchain_core.tools import tool

from app.database.session import AsyncSessionLocal
from app.services import TaskService
from app.tools.schemas import (
    CompleteTaskInput,
    CompleteTaskResponse,
    CreateTaskInput,
    CreateTaskResponse,
    DeleteTaskInput,
    DeleteTaskResponse,
    ListTasksInput,
    ListTasksResponse,
    ReopenTaskInput,
    ReopenTaskResponse,
    TaskOutput,
    UpdateTaskInput,
    UpdateTaskResponse,
)


@tool("create_task", args_schema=CreateTaskInput)
async def create_task(
    title: str,
    description: str | None = None,
    due_date: date | None = None,
    priority: str = "medium",
) -> str:
    """Create a new task with a title, optional description and due date,
    and a priority. Priority can be low, medium, or high."""
    async with AsyncSessionLocal() as session:
        service = TaskService(session)

        task = await service.create_task(
            title=title,
            description=description,
            due_date=due_date,
            priority=priority,
        )

        response = CreateTaskResponse(
            message=f"Task '{task.title}' created successfully.",
            task=TaskOutput.model_validate(task),
        )

        return response.model_dump_json()


@tool("list_tasks", args_schema=ListTasksInput)
async def list_tasks(
    status: str | None = None,
    priority: str | None = None,
) -> str:
    """Retrieve tasks from the task manager.
    Optionally filter by status (pending, in_progress, completed)
    and priority (low, medium, high)."""
    async with AsyncSessionLocal() as session:
        service = TaskService(session)

        tasks = await service.list_tasks(
            status=status,
            priority=priority,
        )

        response = ListTasksResponse(
            count=len(tasks),
            tasks=[
                TaskOutput.model_validate(task)
                for task in tasks
            ],
        )

        return response.model_dump_json()


@tool("update_task", args_schema=UpdateTaskInput)
async def update_task(
    task_id: str,
    updates: dict,
) -> str:
    """Update the details of an existing task.
    Provide a task ID and an updates object containing at least
    one field. Supported fields: title, description, due_date,
    and priority. Description and due_date can be set to null
    to clear them."""
    async with AsyncSessionLocal() as session:
        service = TaskService(session)

        task = await service.update_task(
            task_id=task_id,
            updates=updates,
        )

        response = UpdateTaskResponse(
            message=f"Task '{task.title}' updated successfully.",
            task=TaskOutput.model_validate(task),
        )

        return response.model_dump_json()


@tool("delete_task", args_schema=DeleteTaskInput)
async def delete_task(task_id: str) -> str:
    """Request deletion of an existing task.
    Deletion requires explicit human approval.
    This tool does not delete the task."""
    async with AsyncSessionLocal() as session:
        service = TaskService(session)

        # Validate that the task exists.
        task = await service.get_task(task_id)

        response = DeleteTaskResponse(
            task_id=task.id,
            message=(
                f"Deletion requested for task '{task.title}'. "
                "Human approval is required before deletion."
            ),
            task=TaskOutput.model_validate(task),
        )

        # Deliberately do not call service.delete_task().
        return response.model_dump_json()


@tool("complete_task", args_schema=CompleteTaskInput)
async def complete_task(task_id: str) -> str:
    """Mark an existing task as completed."""
    async with AsyncSessionLocal() as session:
        service = TaskService(session)

        task = await service.complete_task(task_id)

        response = CompleteTaskResponse(
            message=f"Task '{task.title}' marked as completed.",
            task=TaskOutput.model_validate(task),
        )

        return response.model_dump_json()


@tool("reopen_task", args_schema=ReopenTaskInput)
async def reopen_task(task_id: str) -> str:
    """Reopen a previously completed task."""
    async with AsyncSessionLocal() as session:
        service = TaskService(session)

        task = await service.reopen_task(task_id)

        response = ReopenTaskResponse(
            message=f"Task '{task.title}' reopened successfully.",
            task=TaskOutput.model_validate(task),
        )

        return response.model_dump_json()


# Single registry for later LangGraph integration.
TASK_TOOLS = [
    create_task,
    list_tasks,
    update_task,
    delete_task,
    complete_task,
    reopen_task,
]
