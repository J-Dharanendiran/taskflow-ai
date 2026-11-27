
import json
import os

import app.tools.task_tools as task_tools
import pytest
import pytest_asyncio
from app.database.base import Base
from app.llm.factory import create_chat_model
from app.services.exceptions import TaskNotFoundError
from app.tools.task_tools import TASK_TOOLS
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LLM_INTEGRATION") != "1",
    reason="Set RUN_LLM_INTEGRATION=1 to run LLM integration tests.",
)


@pytest_asyncio.fixture
async def tool_session_factory(monkeypatch):
    """Provide an isolated SQLite database for LLM tool execution."""

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
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


async def execute_model_tool(prompt: str, expected_tool: str):
    """
    Generate a tool call using Gemma, execute the real tool,
    return its result to Gemma, and obtain the final response.
    """

    llm = create_chat_model()

    llm_with_tools = llm.bind_tools(TASK_TOOLS)

    messages = [
        SystemMessage(
            content=(
                "You are a task management assistant. "
                "Use the available tools when the user requests an operation. "
                "Do not invent task information or IDs. "
                "The delete_task tool only requests deletion; "
                "it does not delete a task. "
                "After executing a tool, explain the result clearly."
            )
        ),
        HumanMessage(content=prompt),
    ]

    # 1. Generate a structured tool call.
    ai_response = await llm_with_tools.ainvoke(messages)

    assert len(ai_response.tool_calls) == 1, (
        f"Expected one tool call, got: {ai_response.tool_calls}"
    )

    assert ai_response.invalid_tool_calls == []

    tool_call = ai_response.tool_calls[0]

    assert tool_call["name"] == expected_tool, (
        f"Expected {expected_tool}, got {tool_call['name']}"
    )

    # 2. Execute the actual registered tool.
    selected_tool = next(
        tool
        for tool in TASK_TOOLS
        if tool.name == tool_call["name"]
    )

    tool_result = await selected_tool.ainvoke(
        tool_call["args"]
    )

    parsed_result = json.loads(tool_result)

    # 3. Return the result to Gemma.
    messages.extend([
        ai_response,
        ToolMessage(
            content=tool_result,
            tool_call_id=tool_call["id"],
            name=tool_call["name"],
        ),
    ])

    # 4. Generate the final assistant response.
    final_response = await llm.ainvoke(messages)

    assert final_response.content
    assert not final_response.tool_calls

    return parsed_result, final_response.content


# -------------------------------------------------------------------
# CREATE TASK
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_creates_task_through_real_tool_execution(
    tool_session_factory,
):
    result, final_response = await execute_model_tool(
        "Create a task titled 'Prepare project report' "
        "with high priority.",
        "create_task",
    )

    task = result["task"]

    assert task["title"] == "Prepare project report"
    assert task["priority"] == "high"

    # Independently verify database persistence.
    stored = json.loads(
        await task_tools.list_tasks.ainvoke({})
    )

    assert stored["count"] == 1
    assert stored["tasks"][0]["title"] == "Prepare project report"
    assert stored["tasks"][0]["priority"] == "high"

    print("\nCreate task response:", final_response)
    print("Persisted task:", task)


# -------------------------------------------------------------------
# LIST TASKS
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_lists_completed_tasks(
    tool_session_factory,
):
    # Seed two tasks using the actual tools.
    completed = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Completed project report",
        })
    )

    await task_tools.complete_task.ainvoke({
        "task_id": completed["task"]["id"],
    })

    await task_tools.create_task.ainvoke({
        "title": "Pending Python assignment",
    })

    result, final_response = await execute_model_tool(
        "Show me all my completed tasks.",
        "list_tasks",
    )

    assert result["count"] == 1
    assert result["tasks"][0]["title"] == "Completed project report"
    assert result["tasks"][0]["status"] == "completed"

    print("\nList tasks response:", final_response)
    print("Returned tasks:", result)


# -------------------------------------------------------------------
# UPDATE TASK
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_updates_task_priority(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Prepare presentation",
            "priority": "low",
        })
    )

    task_id = created["task"]["id"]

    result, final_response = await execute_model_tool(
        f"Change the priority of task ID {task_id} to high.",
        "update_task",
    )

    task = result["task"]

    assert task["id"] == task_id
    assert task["title"] == "Prepare presentation"
    assert task["priority"] == "high"

    # Verify persisted state independently.
    stored = json.loads(
        await task_tools.list_tasks.ainvoke({})
    )

    assert stored["count"] == 1
    assert stored["tasks"][0]["priority"] == "high"

    print("\nUpdate task response:", final_response)
    print("Updated task:", task)


# -------------------------------------------------------------------
# DELETE TASK
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_requests_task_deletion_without_deleting(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Task awaiting deletion",
        })
    )

    task_id = created["task"]["id"]

    result, final_response = await execute_model_tool(
        f"Request deletion of task ID {task_id}.",
        "delete_task",
    )

    assert result["success"] is True
    assert result["task_id"] == task_id
    assert result["status"] == "pending_approval"

    # Verify the task still exists.
    stored = json.loads(
        await task_tools.list_tasks.ainvoke({})
    )

    assert stored["count"] == 1
    assert stored["tasks"][0]["id"] == task_id

    print("\nDelete request response:", final_response)
    print("Deletion result:", result)


# -------------------------------------------------------------------
# COMPLETE TASK
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_completes_task(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Finish backend integration",
        })
    )

    task_id = created["task"]["id"]

    result, final_response = await execute_model_tool(
        f"Mark task ID {task_id} as completed.",
        "complete_task",
    )

    task = result["task"]

    assert task["id"] == task_id
    assert task["status"] == "completed"
    assert task["completed_at"] is not None

    stored = json.loads(
        await task_tools.list_tasks.ainvoke({
            "status": "completed",
        })
    )

    assert stored["count"] == 1
    assert stored["tasks"][0]["id"] == task_id

    print("\nComplete task response:", final_response)
    print("Completed task:", task)


# -------------------------------------------------------------------
# REOPEN TASK
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_reopens_completed_task(
    tool_session_factory,
):
    created = json.loads(
        await task_tools.create_task.ainvoke({
            "title": "Reopen this task",
        })
    )

    task_id = created["task"]["id"]

    # Establish the completed state first.
    await task_tools.complete_task.ainvoke({
        "task_id": task_id,
    })

    result, final_response = await execute_model_tool(
        f"Reopen the completed task with ID {task_id}.",
        "reopen_task",
    )

    task = result["task"]

    assert task["id"] == task_id
    assert task["status"] == "pending"
    assert task["completed_at"] is None

    stored = json.loads(
        await task_tools.list_tasks.ainvoke({
            "status": "pending",
        })
    )

    assert stored["count"] == 1
    assert stored["tasks"][0]["id"] == task_id

    print("\nReopen task response:", final_response)
    print("Reopened task:", task)


# -------------------------------------------------------------------
# EXECUTION ERROR HANDLING
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_tool_execution_propagates_missing_task_error(
    tool_session_factory,
):
    llm = create_chat_model()

    llm_with_tools = llm.bind_tools(TASK_TOOLS)

    missing_task_id = "00000000-0000-0000-0000-000000000000"

    response = await llm_with_tools.ainvoke([
        SystemMessage(
            content=(
                "You are a task management assistant. "
                "Use the appropriate tool for task operations. "
                "Do not invent task IDs."
            )
        ),
        HumanMessage(
            content=(
                f"Mark task ID {missing_task_id} as completed."
            )
        ),
    ])

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "complete_task"

    selected_tool = next(
        tool
        for tool in TASK_TOOLS
        if tool.name == response.tool_calls[0]["name"]
    )

    # The real tool must propagate the expected service exception.
    with pytest.raises(TaskNotFoundError):
        await selected_tool.ainvoke(
            response.tool_calls[0]["args"]
        )


# -------------------------------------------------------------------
# ERROR RECOVERY
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_explains_tool_execution_failure(
    tool_session_factory,
):
    """Verify that Gemma can explain a real tool execution error."""

    llm = create_chat_model()

    llm_with_tools = llm.bind_tools(TASK_TOOLS)

    missing_task_id = "00000000-0000-0000-0000-000000000000"

    messages = [
        SystemMessage(
            content=(
                "You are a task management assistant. "
                "Use tools for task operations. "
                "Never invent task IDs. "
                "If a tool returns an error, explain the failure clearly. "
                "Never claim an operation succeeded when it failed."
            )
        ),
        HumanMessage(
            content=f"Mark task {missing_task_id} as completed."
        ),
    ]

    # Generate the tool call.
    ai_response = await llm_with_tools.ainvoke(messages)

    assert len(ai_response.tool_calls) == 1
    assert ai_response.tool_calls[0]["name"] == "complete_task"

    tool_call = ai_response.tool_calls[0]

    selected_tool = next(
        tool
        for tool in TASK_TOOLS
        if tool.name == tool_call["name"]
    )

    messages.append(ai_response)

    # Execute the actual tool and capture its failure.
    try:
        result = await selected_tool.ainvoke(tool_call["args"])

        pytest.fail(
            f"Expected TaskNotFoundError, but tool returned: {result}"
        )

    except TaskNotFoundError:
        error_result = {
            "success": False,
            "error": "task_not_found",
            "message": "The requested task does not exist.",
        }

    # Return the error as a tool result.
    messages.append(
        ToolMessage(
            content=json.dumps(error_result),
            tool_call_id=tool_call["id"],
            name=tool_call["name"],
        )
    )

    # Let Gemma explain the failure.
    final_response = await llm.ainvoke(messages)

    assert final_response.content
    assert not final_response.tool_calls

    answer = final_response.content.lower()

    assert any(
        phrase in answer
        for phrase in (
            "not found",
            "does not exist",
            "couldn't find",
            "cannot find",
            "doesn't exist",
        )
    ), f"Gemma did not clearly explain the error: {answer}"

    print("\nError recovery response:")
    print(final_response.content)


# -------------------------------------------------------------------
# CLARIFICATION HANDLING
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_requests_missing_task_id(
    tool_session_factory,
):
    """Gemma must ask for a task ID instead of inventing one."""

    llm = create_chat_model()

    llm_with_tools = llm.bind_tools(TASK_TOOLS)

    response = await llm_with_tools.ainvoke([
        SystemMessage(
            content=(
                "You are a task management assistant. "
                "Never invent missing task IDs. "
                "Ask the user for required information before "
                "calling a tool."
            )
        ),
        HumanMessage(
            content="Mark my task as completed."
        ),
    ])

    assert response.tool_calls == []
    assert response.invalid_tool_calls == []
    assert response.content

    answer = response.content.lower()

    assert (
        "id" in answer
        or "identifier" in answer
    ), f"Gemma did not ask for the missing task ID: {answer}"

    print("\nMissing ID clarification:")
    print(response.content)


@pytest.mark.asyncio
async def test_gemma_clarifies_unsupported_priority(
    tool_session_factory,
):
    """Gemma must not silently replace an unsupported priority."""

    llm = create_chat_model()

    llm_with_tools = llm.bind_tools(TASK_TOOLS)

    response = await llm_with_tools.ainvoke([
        SystemMessage(
            content=(
                "You are a task management assistant. "
                "Supported priorities are low, medium, and high. "
                "Never silently replace an unsupported priority. "
                "Ask for clarification instead."
            )
        ),
        HumanMessage(
            content=(
                "Create a task titled 'Urgent meeting' "
                "with urgent priority."
            )
        ),
    ])

    assert response.tool_calls == []
    assert response.invalid_tool_calls == []
    assert response.content

    answer = response.content.lower()

    assert all(
        priority in answer
        for priority in ("low", "medium", "high")
    ), f"Gemma did not explain supported priorities: {answer}"

    print("\nUnsupported priority clarification:")
    print(response.content)


# -------------------------------------------------------------------
# INTEGRATION STABILITY
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemma_tool_selection_is_consistent_across_repeated_runs(
    tool_session_factory,
):
    """
    Repeat all six tool-selection scenarios three times.

    This test checks tool selection and argument generation only.
    It does not execute the generated tools.
    """

    llm = create_chat_model()

    llm_with_tools = llm.bind_tools(TASK_TOOLS)

    system = SystemMessage(
        content=(
            "You are a task management assistant. "
            "Use the appropriate tool for task operations. "
            "Never invent missing task IDs. "
            "Use the exact supported argument schemas. "
            "Do not call tools for general informational questions."
        )
    )

    cases = [
        {
            "name": "create_task",
            "prompt": (
                "Create a task titled 'Study Python' "
                "with high priority."
            ),
            "expected": "create_task",
            "arguments": {
                "title": "Study Python",
                "priority": "high",
            },
        },
        {
            "name": "list_tasks",
            "prompt": "Show all completed tasks.",
            "expected": "list_tasks",
            "arguments": {
                "status": "completed",
            },
        },
        {
            "name": "update_task",
            "prompt": (
                "Change the priority of task task-123 to high."
            ),
            "expected": "update_task",
            "arguments": {
                "task_id": "task-123",
                "updates": {"priority": "high"},
            },
        },
        {
            "name": "delete_task",
            "prompt": "Request deletion of task task-123.",
            "expected": "delete_task",
            "arguments": {
                "task_id": "task-123",
            },
        },
        {
            "name": "complete_task",
            "prompt": "Mark task task-123 as completed.",
            "expected": "complete_task",
            "arguments": {
                "task_id": "task-123",
            },
        },
        {
            "name": "reopen_task",
            "prompt": "Reopen completed task task-123.",
            "expected": "reopen_task",
            "arguments": {
                "task_id": "task-123",
            },
        },
        {
            "name": "no_tool",
            "prompt": (
                "Explain the difference between low, medium, "
                "and high priority."
            ),
            "expected": None,
            "arguments": {},
        },
    ]

    failures = []
    total = 0

    for repetition in range(1, 4):
        print(f"\nSTABILITY ROUND {repetition}")

        for case in cases:
            total += 1

            response = await llm_with_tools.ainvoke([
                system,
                HumanMessage(content=case["prompt"]),
            ])

            calls = response.tool_calls

            passed = not response.invalid_tool_calls

            if case["expected"] is None:
                passed = passed and len(calls) == 0
            else:
                passed = passed and (
                    len(calls) == 1
                    and calls[0]["name"] == case["expected"]
                )

                if passed:
                    actual_args = calls[0]["args"]

                    for key, expected_value in case["arguments"].items():
                        if actual_args.get(key) != expected_value:
                            passed = False
                            break

            status = "PASS" if passed else "FAIL"

            print(f"{case['name']}: {status}")

            if not passed:
                failures.append({
                    "round": repetition,
                    "case": case["name"],
                    "calls": calls,
                    "invalid_calls": response.invalid_tool_calls,
                })

    print("\nSTABILITY SUMMARY")
    print(f"Total scenarios: {total}")
    print(f"Passed: {total - len(failures)}")
    print(f"Failed: {len(failures)}")

    if failures:
        print("\nFAILURE DETAILS:")
        for failure in failures:
            print(failure)

    assert not failures, (
        f"Gemma produced {len(failures)} inconsistent results "
        f"across {total} scenarios."
    )
