
"""Sequential LangGraph tool execution for TaskFlow AI."""

import json
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from app.agent.error_policy import MAX_TRANSIENT_RETRIES, should_retry
from app.agent.state import AgentState
from app.database.session import AsyncSessionLocal
from app.services.deletion_approval_service import DeletionApprovalService
from app.tools.schemas import DeleteTaskResponse, TaskOutput
from app.tools.task_tools import TASK_TOOLS

TOOLS_BY_NAME = {task_tool.name: task_tool for task_tool in TASK_TOOLS}


def _serialize_result(result: Any) -> str:
    """Convert a tool result into serializable message content."""

    if isinstance(result, str):
        return result

    return json.dumps(result, default=str)


def _create_tool_message(
    *,
    tool_call_id: str,
    tool_name: str,
    content: str,
    is_error: bool = False,
) -> ToolMessage:
    """Create a tool result with a stable ID for later replacement."""

    return ToolMessage(
        id=f"tool-result:{tool_call_id}",
        content=content,
        name=tool_name,
        tool_call_id=tool_call_id,
        status="error" if is_error else "success",
    )


def _get_thread_id(config: RunnableConfig) -> str:
    """Read the conversation thread ID from LangGraph configuration."""

    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id")

    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("A valid thread_id is required for deletion requests.")

    return thread_id


async def _execute_regular_tool(
    tool: Any,
    arguments: dict[str, Any],
    config: RunnableConfig,
) -> Any:
    """Validate and execute an ordinary task tool with transient retries."""

    if tool.args_schema is not None:
        validated_arguments = tool.args_schema.model_validate(arguments)
        arguments = validated_arguments.model_dump(mode="python")

    retries_used = 0

    while True:
        try:
            return await tool.ainvoke(arguments, config=config)

        except Exception as error:
            if not should_retry(
                error,
                retries_used=retries_used,
                max_retries=MAX_TRANSIENT_RETRIES,
            ):
                raise

            retries_used += 1


async def _create_deletion_request(
    arguments: dict[str, Any],
    *,
    thread_id: str,
    execution_id: str,
    tool_call_id: str,
) -> tuple[str, dict[str, str]]:
    """Create a durable approval request without deleting the task."""

    tool = TOOLS_BY_NAME["delete_task"]

    if tool.args_schema is not None:
        validated_arguments = tool.args_schema.model_validate(arguments)
        arguments = validated_arguments.model_dump(mode="python")

    task_id = arguments["task_id"]

    async with AsyncSessionLocal() as session:
        service = DeletionApprovalService(session)

        created = await service.create_request(
            task_id=task_id,
            thread_id=thread_id,
            execution_id=execution_id,
            tool_call_id=tool_call_id,
        )

        task = await service.tasks.get_task(task_id)

        response = DeleteTaskResponse(
            task_id=task_id,
            deletion_request_id=created.deletion_request.id,
            approval_id=created.approval.id,
            message="Deletion requested. Explicit human approval is required.",
            task=TaskOutput.model_validate(task),
        )

        pending_approval = {
            "approval_id": created.approval.id,
            "deletion_request_id": created.deletion_request.id,
            "task_id": task_id,
            "tool_call_id": tool_call_id,
        }

        return response.model_dump_json(), pending_approval


async def tool_executor_node(
    state: AgentState,
    config: RunnableConfig,
) -> dict:
    """Execute the latest AI message's tool calls sequentially."""

    if state["pending_approval"] is not None:
        raise ValueError(
            "Cannot execute new tool calls while an approval is pending."
        )

    if not state["messages"]:
        raise ValueError("Cannot execute tools without conversation messages.")

    ai_message = state["messages"][-1]
    tool_calls = getattr(ai_message, "tool_calls", None)

    if not tool_calls:
        raise ValueError("The latest AI message contains no tool calls.")

    execution_id = state["execution_id"]
    messages: list[ToolMessage] = []
    pending_approval = None

    for tool_call in tool_calls:
        tool_call_id = tool_call["id"]
        tool_name = tool_call["name"]
        arguments = tool_call["args"]

        try:
            if tool_name not in TOOLS_BY_NAME:
                raise ValueError(f"Unknown tool: {tool_name}")

            if tool_name == "delete_task":
                if pending_approval is not None:
                    raise ValueError(
                        "Only one deletion request can be submitted "
                        "per assistant tool-call batch."
                    )

                result, pending_approval = await _create_deletion_request(
                    arguments,
                    thread_id=_get_thread_id(config),
                    execution_id=execution_id,
                    tool_call_id=tool_call_id,
                )

            else:
                result = await _execute_regular_tool(
                    TOOLS_BY_NAME[tool_name],
                    arguments,
                    config,
                )

            messages.append(
                _create_tool_message(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    content=_serialize_result(result),
                )
            )

        except Exception as error:
            messages.append(
                _create_tool_message(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    content=f"Tool '{tool_name}' failed: {error}",
                    is_error=True,
                )
            )

    result = {"messages": messages}

    if pending_approval is not None:
        result["pending_approval"] = pending_approval
        result["execution_status"] = "waiting_for_approval"

    return result
