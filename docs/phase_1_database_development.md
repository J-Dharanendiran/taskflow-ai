# TaskFlow AI --- Phase 1: Database Development

**Status:** Completed\
**Phase:** 1 --- Database Development

## 1. Objective

Build a reliable persistence layer for TaskFlow AI that supports task
creation, retrieval, updating, completion, reopening, and deletion while
enforcing data constraints, maintaining transaction consistency, and
handling timestamps consistently in UTC.

## 2. Technology stack

  Technology       Purpose
  ---------------- ------------------------------
  Python 3.12.7    Backend runtime
  SQLAlchemy 2.x   ORM and database interaction
  aiosqlite        Asynchronous SQLite driver
  SQLite           Persistent local database
  Alembic          Database schema migrations
  pytest           Automated testing
  pytest-asyncio   Asynchronous test support

Database file: `data/taskflow.db`.

## 3. Database infrastructure

Implemented under `backend/app/database/`:

-   `base.py` --- SQLAlchemy declarative base.
-   `session.py` --- asynchronous engine and `AsyncSessionLocal` session
    factory.
-   `dependencies.py` --- asynchronous `get_db()` session dependency.
-   `types.py` --- custom `UTCDateTime` SQLAlchemy type.

The session dependency yields and closes a session but does not
automatically commit. Transaction ownership belongs to the service
layer.

### UTC datetime handling

SQLite does not reliably preserve timezone metadata in datetime columns.
`UTCDateTime` therefore:

1.  Rejects naive datetime values.
2.  Converts timezone-aware values to UTC before storage.
3.  Stores the UTC value without timezone metadata.
4.  Restores UTC timezone information when reading values.

The Task model uses this type for `created_at`, `updated_at`, and
`completed_at`.

## 4. Task data model

Implemented in `backend/app/models/task.py`.

The `tasks` table contains nine columns:

  Column           Type            Nullable Purpose
  ---------------- ------------- ---------- ----------------------------
  `id`             String(36)            No UUID primary key
  `title`          String(255)           No Task title
  `description`    Text                 Yes Optional description
  `due_date`       Date                 Yes Optional calendar due date
  `priority`       String(10)            No Task priority
  `status`         String(20)            No Task lifecycle status
  `created_at`     UTCDateTime           No Creation timestamp
  `updated_at`     UTCDateTime           No Last-update timestamp
  `completed_at`   UTCDateTime          Yes Completion timestamp

Model behavior and defaults:

-   UUID string generated for each task.
-   Priority defaults to `medium`.
-   Status defaults to `pending`.
-   Creation and update timestamps use `utc_now()`.
-   `updated_at` is refreshed by SQLAlchemy on updates.
-   `completed_at` is nullable until completion.
-   `due_date` is a calendar date, not a datetime.

## 5. Constraints and indexes

Three database-level check constraints were added:

  -----------------------------------------------------------------------
  Constraint                          Rule
  ----------------------------------- -----------------------------------
  `ck_tasks_title_not_empty`          `length(trim(title)) > 0`

  `ck_tasks_valid_priority`           Priority is `low`, `medium`, or
                                      `high`

  `ck_tasks_valid_status`             Status is `pending`, `in_progress`,
                                      or `completed`
  -----------------------------------------------------------------------

Three indexes were created:

-   `ix_tasks_status`
-   `ix_tasks_priority`
-   `ix_tasks_due_date`

## 6. Alembic migrations

Alembic was initialized with its asynchronous template and configured to
use the centralized database URL and `Base.metadata`. The Task model is
imported so its table is registered for migration autogeneration.

Initial migration:

`e08e4db1d85c_create_tasks_table.py`

Applied using:

``` powershell
alembic upgrade head
```

The resulting SQLite schema was inspected directly. The table, columns,
defaults, constraints in the migration, and indexes were checked.

The model/schema comparison was run using:

``` powershell
alembic check
```

Result:

``` text
No new upgrade operations detected.
```

No additional migration was required after introducing `UTCDateTime`,
because its underlying SQLAlchemy database implementation remains
`DateTime`.

## 7. Repository layer

Implemented in `backend/app/repositories/task_repository.py`.

`TaskRepository` receives an existing `AsyncSession` and provides:

  Method                 Responsibility
  ---------------------- ----------------------------------------------------
  `create(task)`         Add a task, flush, and refresh the inserted object
  `get_by_id(task_id)`   Retrieve a task by primary key
  `get_all()`            Retrieve tasks, newest first
  `update(task)`         Flush changes to the current transaction
  `delete(task)`         Delete a task and flush the deletion

The repository does not commit or roll back. It operates within the
session and transaction supplied by the service.

## 8. Service layer

Implemented in `backend/app/services/task_service.py`.

### Operations

  -----------------------------------------------------------------------
  Method                              Responsibility
  ----------------------------------- -----------------------------------
  `create_task()`                     Validate and create a task

  `get_task()`                        Retrieve a task or raise
                                      `TaskNotFoundError`

  `list_tasks()`                      Return all tasks

  `update_task()`                     Validate and update permitted
                                      fields

  `complete_task()`                   Mark a task completed and set its
                                      completion timestamp

  `reopen_task()`                     Set status to pending and clear
                                      completion timestamp

  `delete_task()`                     Delete a task
  -----------------------------------------------------------------------

### Validation rules

-   Title must be a string, non-empty after trimming, and no longer than
    255 characters.
-   Priority must be `low`, `medium`, or `high`.
-   Due date must be a `date` value or `None`; `datetime` values are
    rejected.
-   Description must be a string or `None`.
-   Updates must be dictionaries.
-   Only `title`, `description`, `due_date`, and `priority` can be
    updated through `update_task()`.

### Lifecycle rules

-   New tasks default to `pending` and `medium` priority.
-   Completing a task sets status to `completed` and records
    `completed_at`.
-   Completing an already completed task preserves its original
    completion timestamp.
-   Reopening sets status to `pending` and clears `completed_at`.
-   Updating a task refreshes `updated_at`.

### Transaction ownership

The service owns `commit()` and `rollback()`:

1.  It performs writes through the repository.
2.  It commits on success.
3.  It rolls back if an exception occurs.
4.  It re-raises the exception for the caller to handle.

This separates database access from business rules and transaction
ownership.

### Service exceptions

-   `TaskServiceError`
-   `TaskNotFoundError`
-   `InvalidTaskDataError`

## 9. Testing and verification

### Repository unit tests

File: `backend/tests/unit/test_task_repository.py`

Coverage includes creation, retrieval, missing records, listing,
updating, deletion, rollback, database rejection of empty titles and
invalid priorities, and UTC-aware creation/update timestamps.

**Result: 11 passed.**

### Service unit tests

File: `backend/tests/unit/test_task_service.py`

Coverage includes default/custom creation, title and priority
validation, retrieval, listing, updates, invalid update fields,
completion/reopening, deletion, timestamp behavior, rollback after
simulated commit failures, and due-date type validation.

**Result: 23 passed.**

### Real database integration test

File: `backend/tests/integration/test_task_database.py`

The test uses the application's configured `AsyncSessionLocal` and
actual SQLite database. It verifies:

1.  Create a task.
2.  Retrieve the task.
3.  Update the task.
4.  Complete the task.
5.  Reopen the task.
6.  Delete the task.
7.  Verify retrieval raises `TaskNotFoundError`.

**Result: 1 passed.**

### Final verification

  Test group                     Passed
  ---------------------------- --------
  Repository unit tests              11
  Service unit tests                 23
  Database integration tests          1
  **Total**                      **35**

Commands used:

``` powershell
python -m pytest tests/unit -v
python -m pytest tests/integration/test_task_database.py -v
alembic check
```

Recorded results:

-   34 unit tests passed.
-   1 real-database integration test passed.
-   Alembic reported no pending schema changes.

**Total: 35 passing tests.**

## 10. Architecture and decisions

``` text
Application Layer
       |
       v
  TaskService
(business rules and
transaction ownership)
       |
       v
 TaskRepository
  (data access)
       |
       v
  AsyncSession
       |
       v
     SQLite
```

  Area                        Decision
  --------------------------- ---------------------------------
  Database                    SQLite
  ORM                         SQLAlchemy 2.x
  Driver                      aiosqlite
  Database access             Asynchronous
  Migrations                  Alembic
  Primary key                 UUID stored as String(36)
  Timestamp standard          UTC
  Repository responsibility   Database access
  Service responsibility      Business rules and transactions
  Constraints                 Check constraints
  Testing                     Unit and integration tests

## 11. Scope boundaries

The current phase deliberately implements a focused task model. The
following were not added:

-   Multiple users or user-specific data isolation.
-   Recurring tasks.
-   Subtasks.
-   Tags or categories.
-   Attachments.
-   Complex scheduling.

These are outside the current scope and should not be added without a
concrete requirement.

Deletion approval is not implemented in the database service. The
service provides deletion functionality; approval of destructive actions
belongs to the agent interaction/orchestration layer.

## 12. Phase completion assessment

Phase 1 delivered:

-   A configured SQLite database.
-   A SQLAlchemy Task model.
-   An Alembic-managed schema.
-   A repository for database operations.
-   A service for business rules and transactions.
-   UTC-aware timestamp handling.
-   Unit and real-database integration test coverage.

The recorded verification baseline is **35 passing tests**, with no
pending Alembic schema changes.

**Phase 1 --- Database Development: Completed.**

## 13. Handoff to Phase 3

Phase 1 is Tool Development.

The next phase will expose existing TaskService capabilities through
LLM-callable tools. Tools should call the service rather than accessing
SQLAlchemy sessions or the database directly.

Intended boundary:

``` text
LLM
 |
 v
LangChain Tools
 |
 v
TaskService
 |
 v
TaskRepository
 |
 v
SQLite
```

The service remains the source of truth for task validation, business
rules, and transaction handling. Destructive-action approval must be
enforced by the agent interaction/orchestration layer, not delegated to
the LLM itself.
