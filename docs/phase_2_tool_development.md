# TaskFlow AI --- Phase 2: Tool Development

**Status:** Completed\
**Phase:** 2 --- Tool Development\
**Predecessor:** Phase 1 --- Database Development\
**Successor:** Phase 3 --- LLM Integration

## 1. Objective

Expose the existing TaskFlow AI task-management capabilities as
structured, LLM-callable tools.

The tool layer provides a controlled interface between the language
model and the application's existing business logic. It must not
duplicate task validation, business rules, transaction handling, or
database access.

## 2. Technology stack

  Technology       Purpose
  ---------------- --------------------------------------------
  Python 3.12.7    Backend runtime
  LangChain Core   Structured tool definitions and invocation
  Pydantic         Tool argument schemas and validation
  SQLAlchemy 2.x   Existing asynchronous persistence layer
  pytest           Automated testing
  pytest-asyncio   Asynchronous test support

The tools are implemented under `backend/app/tools/` and reuse the
service layer from Phase 1.

## 3. Architecture and responsibility boundaries

``` text
LLM / Agent
    |
    v
LangChain Structured Tools
    |
    v
TaskService
    |
    v
TaskRepository
    |
    v
AsyncSession
    |
    v
SQLite
```

Responsibilities:

-   **Tool layer:** Defines tool names, descriptions, argument schemas,
    and invocation boundaries.
-   **Service layer:** Owns business rules, validation, transaction
    handling, and service exceptions.
-   **Repository layer:** Performs database access through the supplied
    asynchronous session.
-   **Database layer:** Persists task records and enforces database
    constraints.

Tools must call `TaskService`; they must not bypass it by directly
implementing SQL queries or business rules.

## 4. Implemented tools

The tool registry is `TASK_TOOLS`, defined in
`backend/app/tools/task_tools.py`.

It contains six `StructuredTool` instances:

  -----------------------------------------------------------------------
  Tool                    Purpose                 Main arguments
  ----------------------- ----------------------- -----------------------
  `create_task`           Create a task           `title` (required),
                                                  optional `description`,
                                                  `due_date`, `priority`

  `list_tasks`            Retrieve tasks with     Optional `status`,
                          optional filters        `priority`

  `update_task`           Update permitted task   `task_id`, `updates`
                          fields                  

  `delete_task`           Request deletion of a   `task_id`
                          task                    

  `complete_task`         Mark a task as          `task_id`
                          completed               

  `reopen_task`           Reopen a completed task `task_id`
  -----------------------------------------------------------------------

### 4.1 Argument contracts

**Create task**

-   `title` is required.
-   `description` is optional.
-   `due_date` is optional and uses an ISO calendar-date representation.
-   `priority` is optional and supports `low`, `medium`, or `high`; the
    default is `medium`.

**List tasks**

-   `status` is optional and supports `pending`, `in_progress`, or
    `completed`.
-   `priority` is optional and supports `low`, `medium`, or `high`.
-   Omitting filters requests an unfiltered task list.

**Update task**

-   `task_id` identifies the task.
-   `updates` is a nested object.
-   Supported update fields are `title`, `description`, `due_date`, and
    `priority`.
-   The service remains responsible for validating the update.

**Delete, complete, and reopen**

-   Each operation requires a `task_id`.
-   Missing task records are reported through the service's
    `TaskNotFoundError` path.

## 5. Destructive-action boundary

Deletion is deliberately different from the other task operations.

Calling `delete_task` does **not** delete the record. It returns a
result with `status="pending_approval"` and leaves the task in the
database.

This preserves the application's human-approval requirement. The LLM can
request deletion, but it cannot authorize or perform the destructive
action merely by selecting the tool.

The approval interaction and the eventual approved deletion belong to
the agent/orchestration layer and are not implemented by this phase.

## 6. Error handling

The tools rely on the service layer for domain validation and error
reporting.

Relevant service exceptions include:

-   `TaskServiceError`
-   `TaskNotFoundError`
-   `InvalidTaskDataError`

The tool layer must not silently convert failed service operations into
successful results. Errors should remain available to the calling
agent/application for appropriate handling.

## 7. Testing and verification

Tool tests use an isolated in-memory SQLite database. The test fixture
replaces the tool module's `AsyncSessionLocal` with a test session
factory, allowing the real tool invocation path to be exercised without
modifying the persistent application database.

Coverage includes:

-   Tool registration and expected tool definitions.
-   Valid argument handling.
-   Task creation, listing, updating, completion, reopening, and
    deletion-request behavior.
-   Optional list filters.
-   Invalid or unsupported input.
-   Missing task identifiers and missing task records.
-   Verification that deletion requests do not delete records.
-   Service-layer behavior through the tool boundary.

### Final verification baseline

At the end of Phase 2, the regular backend regression suite had a
recorded baseline of **69 passing tests**.

The later Phase 3 LLM integration tests are separately gated and are not
part of this regular-suite count.

> The 69-test figure is the recorded full regression baseline at the
> Phase 2/Phase 3 boundary. It should not be interpreted as 69 tool-only
> tests.

## 8. Key design decisions

  -----------------------------------------------------------------------
  Area                                Decision
  ----------------------------------- -----------------------------------
  Tool interface                      LangChain `StructuredTool`

  Tool registry                       Central `TASK_TOOLS` list

  Business logic                      Reuse `TaskService`

  Database access                     Indirect, through the service and
                                      repository

  Argument validation                 Structured schemas plus service
                                      validation

  Task filters                        Optional status and priority

  Deletion                            Request only; approval required

  Test database                       Isolated in-memory SQLite

  Test strategy                       Exercise actual tool invocation and
                                      verify persisted state
  -----------------------------------------------------------------------

## 9. Scope boundaries

This phase delivers the callable task-tool layer. It does not deliver:

-   LLM selection of tools.
-   A conversational agent or production agent loop.
-   LangGraph orchestration.
-   Graph state management or checkpointing.
-   Multi-turn conversation persistence.
-   The human approval workflow for completing a deletion.
-   Frontend integration.

Those responsibilities belong to later phases.

## 10. Phase completion assessment

Phase 2 delivered:

-   Six structured task-management tools.
-   A central `TASK_TOOLS` registry.
-   Explicit argument contracts.
-   Reuse of the existing service layer.
-   A deletion-request boundary that preserves human approval.
-   Automated tests covering the tool layer and its interaction with
    task services.

**Phase 2 --- Tool Development: Completed.**

## 11. Handoff to Phase 3 --- LLM Integration

Phase 3 connects Gemma 4 through Ollama and LangChain to the existing
tool registry.

The LLM should:

1.  Receive a user request.
2.  Select a tool when the request clearly maps to a supported
    operation.
3.  Produce arguments matching that tool's schema.
4.  Allow the application to execute the selected tool.
5.  Receive the tool result.
6.  Produce a user-facing response or ask for missing/invalid
    information.

The LLM must not bypass tool contracts or be treated as the authority
for destructive-action approval.

The six tools and their service-layer behavior are the Phase 3
integration boundary. Changes to their contracts should be
evidence-driven and coordinated with the tool tests.
