
from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

TaskPriority = Literal["low", "medium", "high"]
TaskStatus = Literal["pending", "in_progress", "completed"]


class ToolInput(BaseModel):
    """Base configuration for tool input schemas."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------
# Input schemas
# --------------------------------------------------


class CreateTaskInput(ToolInput):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_date: date | None = None
    priority: TaskPriority = "medium"

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Task title cannot be empty.")
        return value


class ListTasksInput(ToolInput):
    status: TaskStatus | None = None
    priority: TaskPriority | None = None


class TaskUpdateFields(ToolInput):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    due_date: date | None = None
    priority: TaskPriority | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Task title cannot be empty.")
        return value

    @model_validator(mode="after")
    def validate_updates(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")

        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("Task title cannot be None.")

        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("Task priority cannot be None.")

        return self

    def to_updates(self) -> dict:
        return self.model_dump(exclude_unset=True)


class UpdateTaskInput(ToolInput):
    task_id: str = Field(min_length=1)
    updates: dict

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, value: dict) -> dict:
        validated = TaskUpdateFields.model_validate(value)
        return validated.to_updates()


class DeleteTaskInput(ToolInput):
    task_id: str = Field(min_length=1)


class CompleteTaskInput(ToolInput):
    task_id: str = Field(min_length=1)


class ReopenTaskInput(ToolInput):
    task_id: str = Field(min_length=1)


# --------------------------------------------------
# Output schemas
# --------------------------------------------------


class TaskOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    due_date: date | None
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class CreateTaskResponse(BaseModel):
    success: bool = True
    message: str
    task: TaskOutput


class ListTasksResponse(BaseModel):
    success: bool = True
    count: int
    tasks: list[TaskOutput]


class UpdateTaskResponse(BaseModel):
    success: bool = True
    message: str
    task: TaskOutput


class DeleteTaskResponse(BaseModel):
    success: bool = True
    task_id: str
    deletion_request_id: str | None = None
    approval_id: str | None = None
    status: Literal["pending_approval"] = "pending_approval"
    message: str
    task: TaskOutput


class CompleteTaskResponse(BaseModel):
    success: bool = True
    message: str
    task: TaskOutput


class ReopenTaskResponse(BaseModel):
    success: bool = True
    message: str
    task: TaskOutput
