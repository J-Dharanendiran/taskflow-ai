# TaskFlow AI
# Phase 4 — LangGraph Graph Architecture Specification

**Version:** 1.1  
**Status:** Approved and Frozen  
**Phase:** Phase 4 — LangGraph Orchestration  
**Date:** 25 November 2026  
**Predecessor:** Phase 4 — Requirements Specification v1.1  
**Successor:** Phase 5 — State and Message Contracts

---

## 1. Purpose

This document defines the architecture of the LangGraph orchestration layer for TaskFlow AI.

The orchestration layer connects the existing LLM integration, structured task tools, business services, database and conversational interface into one controlled workflow.

The architecture establishes:

- Graph topology.
- Node responsibilities.
- Conditional routing.
- Sequential tool execution.
- Human approval and deletion execution.
- Conversation memory.
- Error recovery.
- Persistent checkpointing.
- FastAPI integration.
- Performance and reliability boundaries.

This document defines the architectural structure. Exact state schemas, message contracts, database schemas and implementation details belong to subsequent design stages.

## 2. Architectural Principles

### 2.1 LLM proposes; application controls

The LLM interprets user requests and proposes tool calls.

The application controls:

- Tool validation.
- Tool execution.
- Authorization.
- Approval.
- Error recovery.
- Workflow termination.

The LLM must never independently authorize destructive operations.

### 2.2 Preserve existing business logic

All task operations must continue through the existing architecture:

`LLM → Structured Tools → TaskService → TaskRepository → AsyncSession → SQLite`

The orchestration layer must not bypass `TaskService` or duplicate business rules.

### 2.3 One unified graph

The system uses one top-level LangGraph workflow organized into modular node groups.

Separate subgraphs are not required initially.

### 2.4 Explicit execution boundaries

Tool execution, approval, deletion and error recovery must have clearly defined responsibilities.

### 2.5 Minimal additional complexity

Do not introduce additional agents, vector databases, external services or unnecessary processing stages.

Every component must serve a concrete requirement.

## 3. High-Level Architecture

The architecture consists of six logical layers.

### 3.1 Presentation Layer

**Frontend**

Responsibilities:

- Submit user messages.
- Maintain the current conversation thread identifier.
- Display assistant responses.
- Display clarification questions.
- Display deletion approval requests.
- Submit approval or rejection decisions.
- Retrieve conversation history.

The frontend must not interact directly with LangGraph.

### 3.2 API Layer

**FastAPI**

Responsibilities:

- Receive chat requests.
- Validate incoming API payloads.
- Validate conversation thread identifiers.
- Invoke the LangGraph workflow.
- Process approval decisions.
- Return structured responses.
- Retrieve conversation history.

### 3.3 Orchestration Layer

**LangGraph**

Responsibilities:

- Manage conversation execution.
- Coordinate LLM interaction.
- Route tool calls.
- Execute tools sequentially.
- Process tool results.
- Handle errors and retries.
- Manage approval interruptions.
- Maintain workflow state.

### 3.4 LLM Layer

**ChatOllama — Gemma 4 E4B**

Responsibilities:

- Interpret user messages.
- Generate responses.
- Request structured tool calls.
- Continue conversations using relevant context.

The LLM does not directly access the database.

### 3.5 Tool Layer

The existing `TASK_TOOLS` registry remains the source of LLM-callable task tools.

Existing tools:

1. `create_task`
2. `list_tasks`
3. `update_task`
4. `delete_task`
5. `complete_task`
6. `reopen_task`

Tools validate inputs and delegate business operations to `TaskService`.

### 3.6 Business and Persistence Layers

**TaskService, TaskRepository, SQLAlchemy and SQLite**

These components retain their existing responsibilities.

The application database remains the source of truth for task records, deletion-request lifecycle records and destructive execution outcomes.

## 4. Graph Topology

The system uses one unified graph with four logical modules:

1. Conversation module.
2. Tool execution module.
3. Approval module.
4. Error recovery module.

The graph contains six logical nodes.

| Node | Module | Responsibility |
|---|---|---|
| Agent | Conversation | Interpret input, generate responses and tool calls |
| Tool Executor | Tool execution | Validate and execute tool calls sequentially |
| Result Handler | Tool execution | Process execution results and prepare agent feedback |
| Error Handler | Error recovery | Classify failures and determine recovery |
| Approval Handler | Approval | Interrupt execution and obtain human approval |
| Deletion Executor | Approval | Execute an approved deletion through TaskService |

Conditional edges control transitions between nodes.

The exact Python function names and internal helper functions will be finalized during implementation design.

## 5. Graph Execution Lifecycle

The normal conversational lifecycle is:

1. Receive a user message.
2. Load the relevant conversation context.
3. Invoke the Agent node.
4. Evaluate the agent output.
5. Route to the appropriate node.
6. Execute requested operations.
7. Process results or errors.
8. Return relevant results to the Agent when further reasoning is required.
9. Generate a final response.
10. Persist the resulting graph state.

Conceptual flow:

```text
START
  |
  v
Agent
  |
  v
Conditional Router
  |
  +---- Final response --------> END
  |
  +---- Clarification ---------> END
  |
  +---- Unsupported request ---> END
  |
  +---- Tool calls
  |        |
  |        v
  |    Tool Executor
  |        |
  |        v
  |    Result Handler
  |        |
  |        +---- Success -------> Agent
  |        |
  |        +---- Failure -------> Error Handler
  |
  +---- Deletion approval
           |
           v
      Approval Handler
           |
           +---- Rejected ------> Agent
           |
           +---- Approved
                   |
                   v
             Deletion Executor
                   |
                   v
              Result Handler
```

Checkpointing applies throughout graph execution. It is a persistence mechanism, not an additional graph node.

## 6. Sequential Tool Execution

### 6.1 Execution Strategy

A custom sequential tool-execution node will be used instead of relying on default parallel ToolNode execution.

The executor must:

1. Receive model-generated tool calls.
2. Preserve their original order.
3. Validate each call against its existing schema.
4. Execute each valid operation sequentially.
5. Capture individual execution results.
6. Associate results with their original tool-call IDs.
7. Preserve successful results if a later operation fails.
8. Return correctly associated ToolMessages to the Agent.

### 6.2 Multiple Operations

A single user request may require multiple operations.

Example:

"Create a task for my assignment, list my pending tasks, and complete the old assignment task."

The executor processes operations sequentially.

Dependencies between operations must be respected.

If one operation fails, subsequent operations follow the defined failure and dependency policy.

The system reports partial success accurately.

It must not claim that all requested operations succeeded when only some were completed.

### 6.3 Transaction Boundary

Sequential tool execution does not imply one transaction across all requested operations.

Each existing service operation retains its established transaction responsibilities.

Automatic rollback of previously successful independent operations is not required.

## 7. Human Approval and Deletion Architecture

### 7.1 Existing Deletion Tool

The existing `delete_task` tool remains request-only.

Its responsibility is to create a pending deletion request.

It must not perform the actual deletion.

### 7.2 Approval Lifecycle

The approved workflow is:

```text
Agent
  |
  v
delete_task
  |
  v
Pending deletion request
  |
  v
Approval Handler
  |
  v
Human approval interrupt
  |
  +---- Rejected
  |       |
  |       v
  |   Record rejection
  |       |
  |       v
  |     Agent
  |
  +---- Approved
          |
          v
    Validate pending request
          |
          v
    Deletion Executor
          |
          v
    TaskService.delete_task()
          |
          v
    Update request outcome
          |
          v
        Agent
```

### 7.3 Approval Validation

Before execution, the application verifies:

- The approval belongs to the correct request.
- The request is still pending and eligible for processing.
- The submitted decision is explicit.
- The associated task still exists.
- The operation has not already been executed.
- The approval ID belongs to the pending workflow associated with the specified thread.

The authorized deletion path must not be exposed as an ordinary LLM-callable tool.

### 7.4 Deletion Request Lifecycle

The application maintains a durable request lifecycle.

| Status | Meaning |
|---|---|
| PENDING | Awaiting approval |
| APPROVED | Approved; execution may proceed |
| REJECTED | Rejected by the user |
| COMPLETED | Deletion succeeded |
| FAILED | Execution failed |
| CANCELLED | Request invalidated or fulfilled elsewhere |
| EXPIRED | Approval was not received before expiry |

Approval and successful execution are separate events.

### 7.5 Deletion Through Another Authorized Route

If another authorized application operation deletes the same task while a request is pending, the outstanding request must be reconciled.

It should become `CANCELLED` with an appropriate reason, such as `fulfilled_elsewhere`.

### 7.6 Idempotency

Resuming a checkpoint or retrying a workflow must not execute the same destructive operation twice.

Deletion execution and request-status updates must be coordinated transactionally wherever they share the application database.

## 8. Clarification and Conversation Continuation

Ordinary clarification must not create a suspended graph execution.

Examples:

- Missing task information.
- Ambiguous task identification.
- Missing deadline.
- Multiple plausible task matches.

In these cases:

1. The Agent identifies the missing information.
2. The Agent asks a clarification question.
3. The current invocation ends.
4. Conversation context is persisted.
5. The next user message starts a new invocation using the same thread.

Deletion approval is different.

It requires a durable LangGraph interrupt so that the original workflow can resume after the user makes a decision.

## 9. Conversation Memory Strategy

### 9.1 Selected Approach

Conversation memory uses:

**Compact conversation summary + recent messages.**

The entire conversation history must not be sent to the LLM on every turn.

### 9.2 Memory Responsibilities

The summary preserves relevant older conversational context.

Recent messages provide immediate conversational context.

The application database remains the source of truth for task records.

Conversation summaries must not replace actual task data or authoritative task identifiers.

### 9.3 Summarization Trigger

Use a hybrid threshold:

- Token budget is the primary trigger.
- Message count is a secondary safeguard.

Exact thresholds will be determined during State and Message Contract design.

### 9.4 Asynchronous Summarization

Summary updates run asynchronously rather than adding another LLM call to every user request.

Requirements:

- Summary updates must be durably scheduled.
- Pending updates must survive application restarts.
- Failed updates must be retryable.
- The last valid summary must remain available.
- If a new summary is unavailable, use the last valid summary and available recent history.
- Avoid duplicate or out-of-order summary updates.
- Do not introduce a separate memory agent, embeddings or vector database.

The asynchronous execution mechanism and its persistence details will be finalized during subsequent design.

## 10. Error Handling and Recovery

The Error Handler classifies failures and determines whether recovery is appropriate.

### 10.1 Error Categories

| Category | Expected handling |
|---|---|
| Validation error | Return actionable feedback; do not retry automatically |
| Missing resource | Inform the user; do not retry automatically |
| Permanent failure | Report failure |
| Transient failure | Allow bounded retry |
| Partial success | Preserve successful results |
| Uncertain execution outcome | Reconcile before retrying |

### 10.2 Retry Policy

- Retry only appropriate transient failures.
- Use bounded attempts.
- Apply backoff where appropriate.
- Never blindly retry an operation with an uncertain side-effect outcome.
- Avoid duplicate task creation or deletion.

The default maximum is two retries for appropriate transient execution failures.

### 10.3 Iteration Limit

The Agent workflow must have a configurable maximum iteration count.

Default:

`max_agent_iterations = 5`

The limit applies per user request.

Approval interruption and resumption must not reset the iteration counter.

The tool execution limit and agent iteration limit are separate controls.

The graph must terminate safely when the limit is reached.

## 11. Persistence Architecture

### 11.1 Selected Strategy

Use LangGraph persistent checkpointing alongside the existing application database.

### 11.2 Responsibility Separation

| Component | Responsibility |
|---|---|
| LangGraph checkpointer | Workflow state, conversation messages, execution progress and pending interrupts |
| Application database | Tasks, business records, deletion-request lifecycle and destructive execution ledger |
| Conversation summary | Compact representation of relevant older conversational context |

The checkpointer restores workflow state.

It must not become the authoritative source for task records or destructive execution outcomes.

### 11.3 Thread Isolation

Each conversation must have a unique `thread_id`.

Different conversations must never share graph state.

The backend must validate that a thread exists before loading or modifying its state.

The current deployment is explicitly single-user and local.

A thread ID is an identifier, not an authentication credential.

### 11.4 Recovery

The system must support:

- Restoring graph state after application restart.
- Resuming pending approval workflows.
- Retaining relevant conversation context.
- Preventing duplicate execution after recovery.
- Preserving consistency between checkpoints and application records.

## 12. Deletion Consistency and Execution Ledger

### 12.1 Persistence Authority

The application database is authoritative for destructive execution outcomes.

LangGraph checkpoints are authoritative for workflow continuation, not for whether a deletion has succeeded.

### 12.2 Execution Workflow

Before executing an approved deletion:

1. Validate the pending deletion request and approval.
2. Create or claim a unique execution record.
3. Check whether an execution has already completed.
4. Execute deletion through `TaskService`.
5. Record the outcome and update the deletion request.
6. Return the recorded result to LangGraph.
7. Persist the resulting graph checkpoint.

### 12.3 Crash Recovery

| Failure point | Recovery behavior |
|---|---|
| Before execution record creation | Validate and begin again |
| After execution record creation, before deletion | Reconcile execution status |
| After deletion, before checkpoint update | Read the execution ledger and return the existing result |
| After checkpoint update | Continue normally |

An `IN_PROGRESS` execution record must not be interpreted as proof of successful deletion.

Recovery must inspect the task and relevant database records before deciding whether execution can safely continue.

### 12.4 Idempotency Requirements

The execution ledger must include:

- Unique execution identifier.
- Associated deletion request identifier.
- Associated task identifier.
- Execution status.
- Execution timestamps.
- Recorded result or failure information.

Duplicate execution attempts must return the existing outcome where appropriate.

The exact schema, uniqueness constraints, transaction boundaries and recovery rules will be finalized during the Human Approval and Error Handling and Checkpointing design stages.

## 13. FastAPI Integration

The frontend communicates with the backend through three endpoints.

Authentication is intentionally excluded from the current local single-user scope.

### 13.1 Chat Endpoint

`POST /api/v1/chat`

Request:

```json
{
  "thread_id": null,
  "message": "Create a task to finish my ML assignment"
}
```

- `thread_id`: nullable; `null` creates a new conversation.
- `message`: required, non-empty.

Response:

```json
{
  "thread_id": "thread_123",
  "message_id": "msg_456",
  "status": "completed",
  "assistant_message": "I've created your ML assignment task.",
  "pending_approval": null
}
```

Possible statuses:

- `completed`
- `clarification_required`
- `approval_required`

For approval-required responses, `pending_approval` includes the approval identifier and a user-readable description.

### 13.2 Approval Endpoint

`POST /api/v1/chat/{thread_id}/approval`

Request:

```json
{
  "approval_id": "approval_789",
  "decision": "approve"
}
```

Allowed decisions:

- `approve`
- `reject`

Response:

```json
{
  "thread_id": "thread_123",
  "approval_id": "approval_789",
  "status": "completed",
  "assistant_message": "The task was successfully deleted."
}
```

Repeated identical submissions return the recorded outcome rather than executing the operation again.

Conflicting decisions for an already processed request are rejected.

### 13.3 History Endpoint

`GET /api/v1/chat/{thread_id}/history`

Example request:

```http
GET /api/v1/chat/thread_123/history?limit=50
```

Example response:

```json
{
  "thread_id": "thread_123",
  "messages": [
    {
      "message_id": "msg_001",
      "role": "user",
      "content": "Create a task to finish my ML assignment",
      "created_at": "2026-11-25T14:30:00Z"
    },
    {
      "message_id": "msg_002",
      "role": "assistant",
      "content": "I've created your ML assignment task.",
      "created_at": "2026-11-25T14:30:03Z"
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

History retrieval must use cursor-based pagination.

### 13.4 Shared API Rules

- Validate request payloads using Pydantic.
- Use UTC ISO 8601 timestamps.
- Return structured errors.
- Keep graph implementation details inside the backend.
- Do not expose raw checkpoints or internal tool execution payloads.
- Validate thread and approval association on every approval operation.
- Prevent duplicate approval execution.

Suggested HTTP status handling:

| Condition | HTTP status |
|---|---:|
| Successful request | 200 |
| New conversation created | 201 |
| Invalid request | 422 |
| Unknown thread or approval | 404 |
| Conflicting approval decision | 409 |
| Unexpected server failure | 500 |

The API is designed for local single-user use.

It does not provide authentication, user ownership or protection against other local processes or users deliberately accessing the application.

## 14. Performance and Latency Requirements

TaskFlow AI must remain responsive.

The architecture must avoid unnecessary model calls, redundant graph transitions and excessive context processing.

### 14.1 Performance Principles

1. Use one primary Agent interaction per reasoning step.
2. Execute requested tools without additional LLM calls between every tool unless further reasoning is genuinely necessary.
3. Do not summarize every conversation turn.
4. Avoid unnecessary state transformations.
5. Keep tool execution sequential without introducing artificial delays.
6. Avoid separate agents and unnecessary subgraphs.
7. Do not retry permanent failures.
8. Keep prompts and conversation context bounded.
9. Run summary updates asynchronously.
10. Do not block the user's response on nonessential background memory maintenance.

### 14.2 Performance Measurement

Measure these separately:

- LLM inference latency.
- Tool execution latency.
- Database operation latency.
- Graph orchestration overhead.
- Total API response latency.
- Summary-generation latency.

Performance must be measured against a baseline.

Conversation summarization and additional orchestration must not be assumed beneficial without evidence.

## 15. Security and Reliability Boundaries

Under the approved local single-user deployment model:

- No registration or login.
- No JWT authentication.
- No authenticated user identity.
- No public multi-user access.
- Validate thread existence.
- Validate approval-to-request association.
- Never accept arbitrary approval decisions without checking the pending request.
- Never expose direct database access to the LLM.
- Never bypass TaskService.
- Require explicit approval for conversational deletion requests.
- Enforce idempotent destructive execution.
- Use bounded retries.
- Reconcile uncertain execution outcomes.
- Report partial success accurately.
- Never fabricate task identifiers or execution results.

If public or multi-user deployment becomes a requirement, authentication, user ownership, authorization and additional security controls must be designed before deployment.

## 16. Scope Boundaries

This architecture does not introduce:

- Multi-agent orchestration.
- New task business operations.
- A new LLM or Ollama model.
- A vector database for conversation memory.
- Calendar integration.
- Email integration.
- Notification systems.
- A new frontend architecture.
- Independent subgraphs without demonstrated need.
- User registration or authentication.

## 17. Architecture Decision Register

All eight graph architecture decisions have been approved.

| ID | Decision | Final selection |
|---|---|---|
| A-01 | Tool execution strategy | Custom sequential executor |
| A-02 | Deletion architecture | Separate approval-gated execution |
| A-03 | Persistence architecture | LangGraph checkpointer + application DB |
| A-04 | Conversation memory | Summary + recent messages |
| A-05 | Graph topology | Unified graph with modular groups |
| A-06 | Node responsibilities | Balanced modular nodes |
| A-07 | Clarification and interruption | Hybrid approach |
| A-08 | API integration | Chat + approval + history endpoints |

Additional approved decisions:

| ID | Decision | Final selection |
|---|---|---|
| M-01 | Memory summarization | Hybrid token/message threshold + asynchronous updates |
| D-01 | Deletion consistency | Database-authoritative execution ledger |
| API-01 | Approval validation | Thread and approval-specific validation; no user authentication |
| API-02 | API contracts | Three defined endpoints |
| AUTH-01 | Authentication | Single-user local application without authentication |

All listed decisions are approved and frozen.

## 18. Implementation Readiness

The Graph Architecture stage establishes the overall structure, boundaries and execution responsibilities.

The following design stages remain:

### Phase 5 — State and Message Contracts

- Define graph state.
- Define message handling.
- Define tool-call tracking.
- Define thread identifiers.
- Define API payloads.
- Define token and message thresholds for memory summarization.

### Phase 6 — Human Approval and Error Handling

- Define approval records.
- Define interrupt/resume contracts.
- Define failure classifications.
- Define retry behavior.
- Define execution ledger schema and idempotency.

### Phase 7 — Checkpointing and Persistence Design

- Finalize checkpointer selection.
- Define persistence.
- Define recovery.
- Define thread lifecycle.
- Define asynchronous summary-job durability and recovery.

### Phase 8 — Implementation and Component Testing

- Implement incrementally.
- Validate each component.
- Run integration and end-to-end tests.
- Verify performance against the baseline.

### Phase 9 — Integration and End-to-End Testing

- Validate the complete graph.
- Test multi-turn conversations.
- Test sequential tool execution.
- Test approval and rejection.
- Test crash recovery.
- Test duplicate execution prevention.
- Test thread isolation.
- Measure end-to-end latency.

No implementation should begin until the required design specifications have been reviewed and frozen.

---

**End of Phase 4 — LangGraph Graph Architecture Specification v1.1**

**Status: Approved and Frozen**