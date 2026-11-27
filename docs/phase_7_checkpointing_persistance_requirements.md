# TaskFlow AI
# Phase 7 — Checkpointing and Persistence Requirements Specification

**Version:** 1.0  
**Status:** Draft — Pending Approval  
**Date:** 26 November 2026  
**Predecessors:** Phase 4 — Graph Architecture v1.1; Phase 5 — State and Message Contracts; Phase 6 — Approval Persistence and Error Handling v1.1  
**Successor:** Phase 8 — Implementation and Component Testing

---

## 1. Objective

Define a simple, reliable persistence mechanism for the TaskFlow AI LangGraph workflow.

The system must preserve conversation execution state, support application restart recovery, and safely resume pending deletion approvals.

The implementation must remain appropriate for a single-user portfolio project.

The primary objective is to demonstrate a functional AI-powered task manager supporting six operations:

1. Create
2. Read
3. Update
4. Delete
5. Complete
6. Reopen

Persistence must support these operations without introducing unnecessary infrastructure or architectural complexity.

## 2. Scope and Design Principles

The following principles govern this phase:

- Keep the existing unified LangGraph architecture.
- Use SQLite for local persistence.
- Use one SQLite database file for application records and LangGraph checkpoints.
- Keep application data and checkpoint responsibilities logically separate.
- Preserve the existing deletion approval and execution safeguards.
- Use bounded conversation history rather than implementing background summarization infrastructure.
- Avoid external persistence services and unnecessary background workers.
- Prefer straightforward, testable recovery behavior.

## 3. Persistence Architecture

The application will use one SQLite database file.

The database contains two logically separate categories of records.

### 3.1 Application-owned records

Managed by the existing SQLAlchemy application architecture.

Responsibilities include:

- Task records.
- Conversation and message records, when implemented.
- Deletion requests.
- Deletion approvals.
- Deletion execution ledger.

### 3.2 LangGraph-managed records

Managed by the LangGraph SQLite checkpointer.

Responsibilities include:

- Graph execution snapshots.
- Conversation-specific graph state.
- Pending interrupt state.
- Workflow continuation information.

The application must not directly manipulate LangGraph internal checkpoint tables.

### 3.3 Persistence ownership

| Component | Authority |
|---|---|
| Application SQLite tables | Tasks, approvals and destructive execution outcomes |
| LangGraph checkpointer | Workflow state and execution continuation |
| AgentState | Current in-memory graph execution context |
| Conversation history | Durable conversation messages |
| Bounded message context | Recent messages supplied to the LLM |

A checkpoint does not prove that an application database operation succeeded.

Application records remain authoritative for business operations.

## 4. Checkpointer Requirements

### CP-01: Persistent SQLite Checkpointer

The application shall use the existing `langgraph-checkpoint-sqlite` dependency.

The checkpointer shall persist graph state in the existing SQLite database.

### CP-02: Thread Isolation

Every conversation shall have a unique `thread_id`.

The same `thread_id` must be supplied through LangGraph configuration whenever accessing or resuming that conversation's graph state.

Different conversations must not share graph execution state.

### CP-03: Checkpoint Persistence

Graph state must remain available after the FastAPI process terminates and restarts.

The implementation must verify that checkpoint data can be written, retrieved and resumed.

### CP-04: Checkpoint Ownership

Checkpoint persistence must remain an internal responsibility of the orchestration layer.

The frontend and API must not directly access raw checkpoint records.

## 5. Application Lifecycle Requirements

### CP-05: Startup Initialization

The FastAPI application shall initialize the SQLite checkpointer during application startup.

The initialized checkpointer shall be made available to the graph runtime.

The graph must not execute before the persistence resources are ready.

### CP-06: Shutdown Cleanup

The application shall close the checkpointer and associated resources during application shutdown.

Connections must not be left open unnecessarily.

### CP-07: Resource Reuse

The application shall reuse its initialized checkpointer rather than creating a new independent checkpointer connection for every graph invocation.

The implementation must follow the actual lifecycle requirements of the selected LangGraph checkpointer version.

## 6. Thread and Conversation Requirements

### CP-08: New Conversation

When a new conversation is created:

1. Generate a unique `thread_id`.
2. Create its durable conversation record.
3. Initialize the graph using that identifier.
4. Persist the resulting checkpoint.

### CP-09: Existing Conversation

When an existing conversation receives a new message:

1. Validate the thread against the application database.
2. Load the relevant bounded conversation context.
3. Initialize the appropriate execution state.
4. Invoke the graph using the existing `thread_id`.

### CP-10: Thread Validation

The backend must reject unknown thread identifiers.

A thread identifier is an identifier, not an authentication credential.

### CP-11: Conversation Continuity

Messages must remain associated with their original conversation.

Checkpoint restoration must not duplicate messages already present in durable conversation history.

## 7. Approval Recovery Requirements

The existing Phase 6 deletion approval architecture remains authoritative.

### CP-12: Persistent Approval Interrupt

When a deletion request requires approval:

1. Create the durable deletion request and approval records.
2. Commit both records.
3. Interrupt the LangGraph execution.
4. Persist the interrupted graph state.

An approval interrupt must not occur before the durable records are committed.

### CP-13: Approval Resume

When the user submits an approval decision:

1. Validate the `thread_id`.
2. Validate the `approval_id` against the same thread.
3. Confirm the durable execution is waiting for that approval.
4. Retrieve the existing checkpoint.
5. Resume the interrupted graph execution.

A new graph execution must not be created for an existing approval resume.

### CP-14: Deletion Safety

Before executing a deletion, the application must verify the durable approval and execution records.

The application must use the existing Phase 6 execution ledger to prevent duplicate deletion.

The LLM must never directly execute the destructive operation.

### CP-15: Restart Recovery

After a backend restart:

- Pending approval workflows must remain recoverable.
- The backend must validate the approval against SQLite before resuming.
- Completed deletion executions must return their recorded result.
- Rejected approvals must never execute deletion.
- An inconsistent checkpoint must not override authoritative application records.

## 8. Checkpoint and Application Data Reconciliation

Checkpoint writes and application database writes are not assumed to be one atomic transaction.

The system must handle the following cases.

| Scenario | Required behavior |
|---|---|
| Checkpoint exists and approval is pending | Validate approval and permit valid resume |
| Checkpoint exists but approval was rejected | Do not execute deletion |
| Checkpoint exists but deletion ledger says COMPLETED | Return existing result without repeating deletion |
| Checkpoint is missing for a pending approval | Return a controlled recovery error; do not create a new deletion execution |
| Checkpoint contains stale approval state | Trust the durable approval record |
| Application execution record is missing | Do not assume the operation succeeded |

Recovery must be deterministic and must not blindly repeat destructive operations.

## 9. Conversation Context Requirements

The initial implementation shall use a bounded recent-message window.

Requirements:

- Load only the configured recent messages into the LLM context.
- Preserve the complete conversation history in durable application storage when conversation-history persistence is implemented.
- Do not append duplicate messages during context initialization.
- Keep the existing Phase 5 `AgentState` contract unchanged.
- Do not introduce additional AgentState fields for checkpoint management.

The context limit shall be configurable.

The exact message-window size can be established during implementation and validated against the local Gemma model.

## 10. Simplified Memory Scope

Asynchronous memory summarization is deferred.

The initial portfolio implementation will not include:

- Durable summary-job scheduling.
- Background summarization workers.
- Summary-job retry infrastructure.
- Summary-job ordering and version management.
- A separate memory service or agent.

The existing `memory_summary` field remains part of the frozen Phase 5 state contract.

It may remain unused or empty in the initial implementation.

This is an explicit scope reduction, not a change to the Phase 5 state schema.

If conversation summarization becomes necessary later, it can be introduced as a separate enhancement.

## 11. Thread and Checkpoint Cleanup

The initial implementation shall not introduce an automated checkpoint cleanup scheduler.

Conversation deletion, if implemented, must not leave the application in a state where the API can access a deleted thread.

Checkpoint cleanup must use the supported capabilities of the selected checkpointer version.

If safe cleanup cannot be implemented without unnecessary complexity, orphaned checkpoint cleanup will be deferred.

## 12. Error Handling

The persistence layer must handle:

- Database connection failures.
- Checkpoint retrieval failures.
- Missing checkpoints.
- Invalid thread identifiers.
- Invalid approval associations.
- Failed checkpoint writes.
- Inconsistent application and checkpoint state.

Failures must return controlled errors.

Unknown or inconsistent execution states must not trigger automatic destructive retries.

Existing Phase 6 error classification and retry rules remain unchanged.

## 13. Explicit Exclusions

The following are outside the initial Phase 7 scope:

- Redis or external checkpoint storage.
- Separate checkpoint database files.
- Multi-user authentication.
- Distributed checkpoint infrastructure.
- Background memory summarization.
- Summary-job scheduling and retry systems.
- Automated checkpoint archival.
- Automated expiration scheduling.
- Advanced checkpoint version management.
- Additional agents or subgraphs.
- Changes to the existing six-node graph topology.
- Changes to the seven-field AgentState contract.

## 14. Acceptance Criteria

Phase 7 is considered complete when the following requirements are satisfied.

### Checkpointer

- [ ] SQLite checkpointer initializes successfully.
- [ ] Checkpoint data persists in the existing database.
- [ ] Checkpoints can be retrieved using the correct `thread_id`.
- [ ] Different threads maintain isolated graph state.
- [ ] Checkpointer resources close correctly during application shutdown.

### Conversation continuity

- [ ] A new conversation receives a unique thread identifier.
- [ ] Existing conversations can continue using their original identifier.
- [ ] Unknown threads are rejected.
- [ ] Recent messages can be restored without duplication.

### Approval recovery

- [ ] A deletion request and approval are committed before graph interruption.
- [ ] Pending approval state survives backend restart.
- [ ] Approval resumes the original interrupted execution.
- [ ] Rejection never executes deletion.
- [ ] Completed deletion is not repeated after checkpoint restoration.
- [ ] Missing or inconsistent checkpoint state produces a controlled error.

### Integration

- [ ] Existing Phase 5 state contracts remain unchanged.
- [ ] Existing Phase 6 approval and error-handling contracts remain unchanged.
- [ ] The existing unified graph architecture is preserved.
- [ ] Ruff checks pass.
- [ ] Relevant unit and integration tests pass.

## 15. Validation Strategy

Testing shall focus on actual application behavior rather than theoretical infrastructure scenarios.

Required tests:

1. Checkpointer initialization.
2. Checkpoint write and retrieval.
3. Thread isolation.
4. Persistence across application restart.
5. Pending approval restoration.
6. Approval resume.
7. Rejected approval behavior.
8. Duplicate deletion prevention.
9. Missing checkpoint handling.
10. FastAPI startup and shutdown lifecycle.

The six task operations must subsequently be validated through the integrated graph and API during Phase 9.

## 16. Design Alignment

This specification preserves the following approved contracts:

- Phase 4: Unified six-node LangGraph architecture.
- Phase 5: Seven-field AgentState and execution lifecycle.
- Phase 6: Durable approval, deletion execution ledger and error classification.

The following is an explicit scope amendment:

- Asynchronous memory summarization is deferred.
- Bounded recent-message context is used initially.
- Application data and LangGraph checkpoint records share one SQLite database file.

No graph topology or existing business-operation contract is changed.

---

**End of Phase 7 Requirements Specification v1.0**

**Approval status:** Pending user review.
