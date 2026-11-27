# TaskFlow AI
# Phase 4 — LangGraph Orchestration Requirements Specification

**Version:** 1.1  
**Status:** Approved and Frozen  
**Phase:** Phase 4 — LangGraph Orchestration  
**Predecessor:** Phase 3 — LLM Integration  
**Successor:** Phase 4 — Graph Architecture  
**Date:** 25 November 2026

---

## 1. Objective

Build a conversational AI task-management system using LangGraph that connects the individually validated components into a controlled, persistent and reliable workflow.

The orchestration layer must enable the agent to:

- Understand natural-language task-management requests.
- Select and execute appropriate task tools.
- Handle multiple operations in one request.
- Maintain multi-turn conversational context.
- Request clarification when information is missing or ambiguous.
- Require human approval for destructive operations.
- Recover from appropriate failures.
- Persist and resume interrupted conversations.
- Generate accurate responses based on actual execution results.

The LLM must not independently control application safety, authorization or business logic.

## 2. Existing System Context

The following components have already been developed and validated.

| Phase | Component | Status |
|---|---|---|
| Phase 1 | Database development | Completed |
| Phase 2 | Structured task tools | Completed |
| Phase 3 | Gemma 4 LLM integration | Completed |
| Phase 4 | LangGraph orchestration | Design completed; implementation pending |

### 2.1 Technology stack

- Python 3.12.7
- FastAPI
- LangGraph
- LangChain Core
- ChatOllama
- Ollama
- Gemma 4 E4B (`gemma4:e4b`)
- SQLite
- SQLAlchemy
- Pydantic
- pytest

### 2.2 Existing task-management tools

The existing `TASK_TOOLS` registry contains:

1. `create_task`
2. `list_tasks`
3. `update_task`
4. `delete_task`
5. `complete_task`
6. `reopen_task`

The orchestration layer must reuse these tools and the existing service layer.

It must not duplicate business logic, validation, transaction handling or database operations.

**Important:** The existing `delete_task` tool creates a pending approval request. It does not perform the actual deletion.

## 3. Functional Requirements

### FR-01: Natural-Language Task Creation

The agent shall understand natural-language requests to create tasks.

Requirements:

- Extract the required task title.
- Extract optional description, due date and priority.
- Invoke `create_task` with valid arguments.
- Request clarification when the title is missing.
- Never invent user-provided task details.

### FR-02: Task Retrieval

The agent shall support retrieving tasks using natural-language requests.

Requirements:

- Invoke `list_tasks` when appropriate.
- Support available status and priority filters.
- Present actual returned task information.
- Never fabricate task records.

### FR-03: Task Updates

The agent shall support updating existing tasks.

Requirements:

- Identify the intended task.
- Identify the fields to update.
- Support title, description, due date and priority modifications.
- Request clarification when task identification is ambiguous.
- Preserve fields that the user did not request to change.

### FR-04: Task Completion

The agent shall support marking tasks as completed.

Requirements:

- Identify the intended task.
- Invoke `complete_task`.
- Report the actual execution result.
- Handle already-completed tasks appropriately.
- Handle missing task records.

### FR-05: Task Reopening

The agent shall support reopening completed tasks.

Requirements:

- Identify the intended task.
- Invoke `reopen_task`.
- Communicate the resulting task status accurately.

### FR-06: Task Deletion and Human Approval

Deletion shall require explicit human authorization.

Requirements:

1. Identify the intended task.
2. Create a pending deletion request.
3. Present the task identity and requested action.
4. Interrupt graph execution while approval is pending.
5. Require explicit approval or rejection.
6. Resume execution following the approval decision.
7. Cancel deletion when rejected.
8. Never interpret silence, timeout or unrelated messages as approval.
9. Associate approval with the correct pending request and task.
10. Prevent duplicate deletion execution.

The existing `delete_task` tool remains request-only.

Actual deletion must occur through a separate approval-gated execution path using `TaskService.delete_task()`.

### FR-07: General Conversation

The agent shall support general conversational questions that do not require task-management operations.

Requirements:

- Answer relevant general questions.
- Explain available capabilities.
- Avoid unnecessary tool invocation.
- Avoid presenting unsupported information as verified fact.

### FR-08: Clarification

The agent shall request clarification when required information is missing or ambiguous.

Requirements:

- Ask focused questions.
- Preserve relevant conversational context.
- Resolve task references using available context and task information.
- Never invent task identifiers.
- Never silently select an uncertain task.

Ordinary clarification shall end the current graph invocation. The next user message shall continue using the same conversation thread.

### FR-09: Tool-Result Communication

The agent shall communicate actual tool execution outcomes.

Requirements:

- Receive and interpret tool results.
- Distinguish successful and failed operations.
- Never claim success when an operation failed.
- Preserve accurate partial-execution information.
- Generate a consolidated response when multiple operations are executed.

### FR-10: Multi-Turn Conversation

The agent shall maintain relevant conversational context.

Requirements:

- Preserve relevant information across turns.
- Resolve contextual references where sufficiently clear.
- Support clarification across multiple messages.
- Maintain separate conversation threads.
- Resume existing conversations.
- Maintain compact conversation memory using summaries and recent messages.

## 4. Multi-Operation Execution Requirements

The system shall support multiple tool calls within one user request.

Approved execution policy:

1. The agent may generate multiple tool calls.
2. Tool arguments must be validated.
3. Tool calls shall execute sequentially.
4. Dependencies between operations must be respected.
5. Each operation must produce a separately identifiable result.
6. The agent shall receive the results and generate a consolidated response.
7. Successful operations must remain distinguishable from failed operations.
8. Partial success must be reported accurately.
9. Multiple operations do not imply automatic database transaction rollback.

Parallel execution is excluded.

A custom sequential executor shall be used rather than relying on default parallel tool execution behavior.

## 5. Task Identification Requirements

The system shall use clear task matching and clarification when necessary.

Rules:

- Use task identifiers internally whenever available.
- Resolve conversational references using available context.
- Proceed when exactly one sufficiently clear match exists.
- Ask the user to choose when multiple plausible matches exist.
- Request clarification when no matching task is found.
- Never fabricate task identifiers.
- Never silently select an uncertain task.
- Always enforce the separate deletion approval requirement.

A single search result must not automatically be considered an unambiguous match.

## 6. Error Handling and Recovery Requirements

The system shall classify failures and apply controlled recovery policies.

| Error category | Required behavior |
|---|---|
| Validation errors | No automatic retry; request corrected input |
| Missing task | No automatic retry; request clarification |
| Transient infrastructure errors | Bounded retry with backoff |
| Permanent errors | No retry; report failure |
| Partial execution | Preserve successful results and report failures |
| Uncertain execution outcome | Verify execution status before retry |
| Destructive operation | Prevent duplicate execution through execution tracking |

Additional requirements:

- Retry limits must be configurable.
- Infinite retries are prohibited.
- Successful operations must not be falsely reported as rolled back.
- Duplicate side effects must be prevented.
- Tool failures must remain visible to the orchestration layer.
- Retry policies must account for the difference between model calls and database mutations.

The default maximum is two retries for appropriate transient failures.

## 7. Agent Execution Limits

The system shall enforce a configurable maximum number of agent iterations.

**Approved default: 5 agent iterations per user request.**

Requirements:

1. Enforce a hard execution limit.
2. Allow configuration of the limit.
3. Define tool-call limits separately.
4. Do not reset iteration counters because of approval interruptions.
5. Terminate safely when the limit is reached.
6. Inform the user when the request cannot be completed within the limit.

## 8. Conversation Persistence and Checkpointing

The system shall use persistent LangGraph checkpointing.

Requirements:

- Every conversation shall have a unique `thread_id`.
- Graph state shall be associated with its conversation thread.
- Checkpoints shall survive application restarts.
- Existing conversations shall be resumable.
- Relevant messages and execution state shall be preserved.
- Pending approval information shall survive interruption.
- Different conversation threads shall remain isolated.
- Checkpoint retention and cleanup policies shall be defined.
- Unnecessary duplication of task database records in graph state shall be avoided.

Checkpointing does not replace application-level conversation management.

The application database remains the source of truth for task records and destructive execution outcomes.

## 9. Conversation Memory Requirements

The system shall use a compact conversation summary combined with recent messages.

Approved strategy:

- Token budget is the primary summarization trigger.
- Message count is a secondary safeguard.
- Summary updates shall run asynchronously.
- Summarization shall not occur on every user message.
- The last valid summary shall remain available.
- Failed summary updates must be recoverable.
- Pending updates must survive application restarts.
- Recent messages shall be retained alongside the summary.
- Summary content must not replace authoritative task records or task identifiers.

Exact thresholds and summary structure shall be defined during State and Message Contract design.

Conversation embeddings, vector databases and separate memory agents are excluded.

## 10. Unsupported Request Handling

The agent shall respect the boundaries of its implemented capabilities.

Requirements:

- Support general conversational questions.
- Explain unsupported external capabilities.
- Never claim to perform unimplemented actions.
- Never invoke unrelated task tools.
- Suggest relevant task-management alternatives when appropriate.
- Never fabricate external information or action results.

Examples of unsupported actions include sending emails, booking flights and accessing external files.

## 11. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | Reuse existing validated service and tool layers. |
| NFR-02 | Maintain conversation isolation. |
| NFR-03 | Prevent uncontrolled agent/tool loops. |
| NFR-04 | Preserve correct message and tool-call ordering. |
| NFR-05 | Support interrupted workflow recovery. |
| NFR-06 | Prevent unauthorized destructive operations. |
| NFR-07 | Provide traceable error handling. |
| NFR-08 | Separate orchestration from business logic. |
| NFR-09 | Maintain compatibility with Gemma 4 and Ollama. |
| NFR-10 | Preserve existing regression-test behavior. |
| NFR-11 | Avoid unnecessary LLM calls and excessive context processing. |
| NFR-12 | Measure and control orchestration latency. |

## 12. Scope Boundaries

### 12.1 Included

- LangGraph workflow orchestration.
- Agent execution and conditional routing.
- Tool execution and result propagation.
- Multi-turn conversational state.
- Multi-operation execution.
- Human approval and deletion handling.
- Error classification and retry policies.
- Agent execution limits.
- Persistent checkpointing and resumption.
- Conversation memory management.
- Unit, integration and end-to-end graph testing.

### 12.2 Excluded

- Creating new task-management business operations.
- Reimplementing database or service-layer logic.
- Replacing Gemma 4 or Ollama.
- Introducing multi-agent architecture.
- Developing a new frontend architecture.
- Adding calendar, email or notification integrations.
- Introducing unrelated productivity functionality.
- User registration and authentication.

## 13. Acceptance Criteria

Phase 4 implementation shall be considered complete only when the following behaviors are demonstrated through testing:

1. Natural-language requests reach the appropriate tools.
2. All six existing tools operate through the graph.
3. Multiple sequential tool calls work correctly.
4. Tool results return to the agent in the correct format.
5. Clarification works across multiple turns.
6. Ambiguous task references are handled safely.
7. Deletion approval and rejection work correctly.
8. Unauthorized deletion is prevented.
9. Tool failures follow the approved recovery policies.
10. Partial execution is reported accurately.
11. Agent execution limits are enforced.
12. Separate conversation threads remain isolated.
13. Checkpoints survive application restarts.
14. Interrupted workflows resume correctly.
15. Duplicate destructive execution is prevented.
16. Conversation summaries update without blocking normal responses unnecessarily.
17. Existing regression tests continue passing.
18. Complete graph integration and end-to-end tests pass.

## 14. Approved Design Decisions

| ID | Design area | Approved decision |
|---|---|---|
| D-01 | Multiple operations | Multiple sequential tool calls |
| D-02 | Task identification | Clear matching; clarify ambiguity |
| D-03 | Conversation context | Persistent history with thread isolation |
| D-04 | Deletion approval | Interrupt graph and resume after explicit approval/rejection |
| D-05 | Error handling | Classified errors and controlled retries |
| D-06 | Iteration limit | Configurable; default 5 |
| D-07 | Checkpointing | Persistent LangGraph checkpoints with thread-based resumption |
| D-08 | Unsupported requests | General conversation with capability boundaries |

All eight decisions are individually approved and frozen.

## 15. Development Methodology

Phase 4 follows this sequence:

1. Requirements and scope.
2. Graph architecture.
3. State and message contracts.
4. Human approval and error handling design.
5. Checkpointing design.
6. Incremental implementation and testing.

Each design stage must be reviewed and approved before proceeding to the next stage.

Implementation is prohibited until the required design documents have been approved and frozen.

## 16. Approval and Freeze

**Status: Approved and Frozen.**

This document establishes the requirements baseline for Phase 4.

Following approval:

- Requirements are frozen.
- Changes require explicit review.
- Graph architecture must use this document as its source of truth.
- No implementation begins until the subsequent design stages are completed and approved.

**Next deliverable:** Phase 4 — LangGraph Graph Architecture Specification.