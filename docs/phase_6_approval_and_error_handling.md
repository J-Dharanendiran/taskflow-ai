# TaskFlow AI — Phase 6: Approval Persistence and Error Handling

**Version:** 1.1  
**Status:** Local validation passed; phase closeout pending implementation-to-acceptance review  
**Date:** 26 November 2026  
**Predecessors:** Phase 4 Graph Architecture v1.1; Phase 5 State Contract  
**Scope:** Durable deletion approval, idempotent deletion execution, and deterministic error classification.

---

## 1. Objective

Define the durable application records and failure policies required before the unified LangGraph workflow can safely interrupt for deletion approval and resume execution.

SQLite is authoritative for approval decisions and destructive execution outcomes. LangGraph state and checkpoints carry workflow context but do not independently authorize deletion.

## 2. Durable Records

Three durable records have separate responsibilities.

### 2.1 DeletionRequest

One record represents one requested deletion.

**Required fields:**

- `id` — `deletion_request_id` (UUID string).
- `task_id` — target task identifier.
- `task_title_snapshot` — title captured when the request is created, ensuring stable approval presentation.
- `thread_id` — conversation that initiated the request.
- `execution_id` — logical user request.
- `tool_call_id` — originating model tool call.
- `status` — lifecycle state.
- `requested_at`, `decided_at`, `completed_at`.
- `failure_code`, `failure_message`, `cancellation_reason` — optional outcome diagnostics.

**Lifecycle:**

- `PENDING → APPROVED → COMPLETED`
- `PENDING → REJECTED`
- `APPROVED → CANCELLED` when the task has been deleted through another authorized route.
- `FAILED` represents a terminal execution failure.
- `EXPIRED` is reserved in the schema. Automatic expiration is not active until an expiration duration and scheduler policy are specified.

### 2.2 DeletionApproval

One approval record is created with each deletion request.

**Fields:**

- `id` — `approval_id` (UUID string).
- `deletion_request_id` — unique foreign key to its request.
- `thread_id`, `execution_id`, `tool_call_id` — correlation boundary.
- `decision` — `PENDING`, `APPROVED`, or `REJECTED`.
- `created_at`, `decided_at`.

**Decision rules:**

- A decision is accepted only when the supplied `thread_id` matches the persisted approval.
- The first explicit decision wins.
- Repeating the same decision is idempotent.
- Submitting the opposite decision is a conflict.
- Missing or cross-thread approval IDs are rejected without changing state.

### 2.3 DeletionExecution

One execution ledger row is permitted per deletion request.

**Fields:**

- `id` — unique execution identifier.
- `deletion_request_id` — unique foreign key to the request.
- `task_id` — target task identifier.
- `status` — `IN_PROGRESS`, `COMPLETED`, `FAILED`, or `CANCELLED`.
- `started_at`, `completed_at` — completion timestamp remains nullable until successful completion.
- `failure_code`, `failure_message` — optional terminal failure details.

**Execution rules:**

1. The executor first creates and commits an `IN_PROGRESS` claim.
2. This makes the execution attempt visible to crash recovery.
3. An `IN_PROGRESS` row is not proof that deletion succeeded.
4. Task deletion, the request transition to `COMPLETED`, and the ledger transition to `COMPLETED` must commit in one application-database transaction.
5. A unique constraint on `deletion_request_id` is the final duplicate-claim guard.

**Recovery behavior:**

- If the graph resumes and finds `COMPLETED`, it returns the recorded result without repeating deletion.
- If it finds `IN_PROGRESS`, it checks whether the task still exists.
- An existing task permits safe continuation.
- A missing task is reconciled as `CANCELLED/fulfilled_elsewhere`, because the atomic deletion transaction cannot have committed without also completing the ledger.

## 3. Approval Execution Rules

1. The LLM may request deletion only through the existing `delete_task` tool.
2. The graph's custom Tool Executor validates the tool arguments and creates the durable request and approval using the current `thread_id`, `execution_id`, and model `tool_call_id`.
3. The graph enters `waiting_for_approval` and interrupts only after both records have committed.
4. The API validates the approval ID against the supplied thread before resuming the checkpoint.
5. The approval handler records the explicit decision in SQLite.
6. Rejection ends the destructive execution path. No deletion call occurs.
7. Approval routes to a separate application-owned Deletion Executor. This executor is not registered in `TASK_TOOLS` and cannot be called by the LLM.
8. Before deletion, the executor checks the persisted approval, request, thread association, task existence, and execution ledger.
9. The executor creates or reuses the unique `IN_PROGRESS` execution claim before attempting deletion.
10. If the task has already disappeared through another authorized route, the request and claim become `CANCELLED` with `fulfilled_elsewhere`. This must not be reported as a deletion performed by this approval.
11. The executor calls `TaskService.delete_task()` and commits the task deletion, request outcome, and transition of the execution claim to `COMPLETED` atomically.

## 4. Error Classification

| Category | Examples | Automatic retry | Handling |
|---|---|---:|---|
| Validation | Pydantic validation, invalid task fields | No | Return an actionable correction request |
| Missing resource | Task not found | No | Ask for clarification or report the missing task |
| Transient | Timeout, connection failure, database operational failure | Up to 2 retries | Bounded retry; preserve prior successful independent operations |
| Permanent | Unknown or non-recoverable application failure | No | Report failure and retain diagnostic context |
| Uncertain outcome | Commit or side-effect result cannot be determined | No blind retry | Reconcile SQLite execution ledger and task existence first |

**Retry policy:**

- Unknown exceptions fail closed as permanent.
- The retry counter counts retries after the initial attempt.
- At most two retries means at most three total attempts.
- The retry helper accepts an explicit `max_retries` override; its default is two.
- Agent iteration count remains separate from tool retry count.
- Database operational errors are considered transient only when the driver message indicates a lock, busy database, timeout, connection, temporary unavailability, or disk I/O condition.
- Other database operational errors fail closed as permanent.

## 5. Partial Success and Sequencing

- Tool calls execute sequentially in model-provided order.
- Each tool result remains correlated to its `tool_call_id`.
- Successful independent operations are not described as rolled back when a later operation fails.
- A dependent operation must not run if its prerequisite failed.
- A transient retry applies only to the failed operation. Earlier successful operations must not be replayed.
- An uncertain destructive outcome must be reconciled against the database ledger before any retry.

## 6. Transaction and Recovery Boundaries

The following transaction boundaries are mandatory:

| Operation | Required transaction behavior |
|---|---|
| Request and approval creation | Commit together |
| Approval decision and request status update | Commit together |
| Execution claim creation | Commit `IN_PROGRESS` before deletion begins |
| Task deletion, request completion, ledger completion | Commit atomically |

Additional recovery rules:

- Checkpoint writes and application database writes are not assumed to be part of one atomic transaction.
- After restart or checkpoint resume, SQLite records remain authoritative.
- A `COMPLETED` ledger short-circuits execution even if the graph checkpoint still points to the deletion executor.
- An `IN_PROGRESS` ledger must be reconciled against task existence. It is never treated as proof of success.
- If the task is absent but the ledger is not `COMPLETED`, the executor must not claim this approval deleted it. It reconciles the request and claim as `CANCELLED/fulfilled_elsewhere`.

## 7. Explicitly Deferred

The following items are outside this phase:

- Automatic expiration duration and scheduler.
- Conversation, message, and execution-history tables and their API contracts.
- Memory summary job persistence and scheduling.
- Multi-user authorization. The application remains single-user and local.
- Cross-database distributed transactions. Application data and the checkpointer remain separate SQLite responsibilities.

## 8. Acceptance Criteria

The implementation must satisfy all of the following:

- [ ] Request and approval records are created durably without deleting the task.
- [ ] Approval IDs cannot be used from another thread.
- [ ] Only explicit approve/reject decisions are accepted.
- [ ] Repeating the same decision is idempotent; conflicting decisions fail.
- [ ] Rejection never deletes the task.
- [ ] Execution without approval is rejected.
- [ ] Task deletion, request completion, and the ledger transition to `COMPLETED` are atomic.
- [ ] Replaying a completed deletion returns the existing ledger result and does not execute again.
- [ ] An `IN_PROGRESS` claim can be resumed safely when the task still exists.
- [ ] Terminal execution failures are recorded on both the request and execution ledger.
- [ ] A missing task is reconciled as fulfilled elsewhere, not falsely reported as deleted by this request.
- [ ] Validation and missing-resource errors are not retried.
- [ ] Transient errors allow at most two retries.
- [ ] Uncertain outcomes are reconciled before retry.

## 9. Local Validation Results

**Validation date:** 26 November 2026

| Validation | Command | Result |
|---|---|---|
| Backend test suite | `uv run pytest backend/tests -q -rs` | 118 passed |
| Failed tests | Included in full-suite run | 0 |
| Skipped tests | Included in full-suite run | 0 |
| Ruff lint | `uv run ruff check backend/app backend/tests` | All checks passed |

**Pytest execution time:** 489.09 seconds (8 minutes, 9 seconds).

The full test suite completed successfully, including the tests that previously encountered Ollama connectivity failures.

These results establish that the current test suite and lint checks pass locally. They do not, by themselves, establish that every acceptance criterion has been independently verified. The implementation-to-acceptance review remains the final closeout step.

## 10. Design Alignment

This phase operationalizes the already-approved Phase 4.2 approval lifecycle and Phase 5 persistence ownership.

It does not change:

- The seven-field `AgentState` contract.
- The six-node graph topology.
- The approved Phase 4 graph architecture.

Phase completion is subject to implementation-to-acceptance review and the successful local migration, lint, and full-suite verification recorded above.

---

**Phase 6 validation summary:** 118 tests passed, Ruff checks passed, and no test failures or skips were reported in the final run.