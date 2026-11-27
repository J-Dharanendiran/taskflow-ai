# TaskFlow AI — Phase 5: LangGraph State Contract

**Status:** Frozen for implementation. Contract fields and lifecycle semantics are fixed; implementation prerequisites and verified source gaps are recorded below.  
**Scope:** Agent runtime state only. This document does not define API schemas, database table schemas, or the complete approval persistence model; those belong to their respective design/implementation work.

## 1. Purpose

Define the minimum runtime state required by the unified TaskFlow AI graph. The state is execution-focused. It carries the context needed while the graph runs; it is not the application's durable source of truth.

## 2. Responsibility boundaries

| Component | Owns |
|---|---|
| SQLite application database | Durable tasks, conversation/message history, execution status, approval/deletion records, and durable memory summary |
| LangGraph state | Current execution context and bounded messages used by the graph |
| LangGraph checkpointer | Graph execution snapshots, including state needed to resume an interrupted approval workflow |
| LangGraph config | `thread_id` and other invocation configuration; `thread_id` is not an AgentState field |
| API layer | `request_id`, request validation, and transport-specific request/response contracts |

The graph state and checkpoint are not substitutes for durable application records. A checkpoint is not proof that a database mutation committed.

## 3. Frozen top-level state schema

The state has exactly seven top-level fields:

| Field | Type | Initial value for a new logical execution | Responsibility |
|---|---|---|---|
| `execution_id` | `str` | Newly generated ID, except when continuing a pending clarification | Identifies one logical user-request execution across its clarification/approval lifecycle |
| `messages` | `Annotated[list[AnyMessage], add_messages]` | Bounded recent context plus the current user message | Runtime conversation and tool interaction context |
| `memory_summary` | `str \| None` | Latest durable summary, or `None` | Runtime copy of the durable conversation summary |
| `iteration_count` | `int` | `0` | Number of agent LLM invocation attempts in this logical execution |
| `execution_status` | `Literal["running", "waiting_for_clarification", "waiting_for_approval", "completed", "failed"]` | `"running"` | Runtime lifecycle status |
| `pending_approval` | `PendingApprovalState \| None` | `None` | Active deletion approval context, if any |
| `pending_clarification` | `PendingClarificationState \| None` | `None` | Active clarification context, if any |

No additional top-level fields are introduced for `thread_id`, `request_id`, `current_user_message`, `conversation_history`, `tool_calls`, or `tool_results`.

## 4. Nested interaction contracts

### 4.1 Pending approval

Only deletion approval is in scope for the current application. The runtime object carries references needed to correlate the pending graph interaction with durable application records and the originating tool call.

```python
class PendingApprovalState(TypedDict):
    approval_id: str
    deletion_request_id: str
    task_id: str
    tool_call_id: str
```

The database remains authoritative for approval status and deletion execution. This state object is not the approval ledger. The approved deletion executor is not exposed as an LLM-callable task tool.

### 4.2 Pending clarification

Ordinary clarification does not use a LangGraph interrupt. The graph returns a clarification response and ends the current invocation. The next user message starts a new graph invocation on the same thread; if it answers the outstanding clarification, it continues the same logical `execution_id`.

```python
class PendingClarificationState(TypedDict):
    question: str
    reason: Literal[
        "missing_information",
        "ambiguous_reference",
        "unsupported_value",
    ]
    original_message_id: str
```

The clarification context must be persisted with the conversation so it remains available to the next invocation. It is cleared when resolved or explicitly superseded by a new request.

## 5. Message contract

- Use native LangChain message objects (`AnyMessage`) in the graph state.
- Use LangGraph's `add_messages` reducer for the `messages` channel.
- `AIMessage` carries model-generated tool calls; `ToolMessage` carries each tool result and must retain the matching `tool_call_id`.
- Preserve the order of tool calls and their corresponding results.
- Never trim an assistant tool-call message while leaving its corresponding tool result (or vice versa) in the model context.
- Keep only bounded recent runtime context. SQLite owns complete durable conversation history.
- Keep the memory summary separate from `messages`; prompt assembly supplies it separately.
- System instructions are prompt-layer inputs, not durable conversation history and not a field in AgentState.
- `add_messages` is not plain list replacement. When a new turn requires replacing/rehydrating the bounded runtime window, use an explicit, tested message-removal/replacement operation compatible with the installed LangGraph version. Do not assume that sending an empty list clears the channel.

## 6. Identity contract

| Identifier | Scope | Location |
|---|---|---|
| `thread_id` | One conversation / checkpoint namespace | LangGraph config and durable conversation record |
| `execution_id` | One logical user request, including its clarification and approval lifecycle | AgentState and durable execution record |
| `request_id` | One HTTP/API request | API layer only |
| `message_id` | One individual message | Message metadata and durable message record |
| `approval_id` | One user approval interaction | Durable approval record and pending approval context |
| `deletion_request_id` | One deletion request | Durable deletion-request record and pending approval context |
| `tool_call_id` | One model-issued tool call | AIMessage, corresponding ToolMessage, and pending approval context where relevant |

A new unrelated user request receives a new `execution_id`. A clarification answer continues the existing logical execution but is submitted as a new graph invocation, not as a LangGraph interrupt resume. An approval decision resumes the interrupted graph execution using its existing checkpoint and `execution_id`.

## 7. Iteration contract

- `iteration_count` counts agent LLM invocation attempts, not graph nodes or tool calls.
- Increment immediately before each agent LLM invocation. A failed invocation still counts as an attempt.
- Tool execution, routing, result handling, approval handling, and clarification handling do not increment the counter.
- A clarification continuation or approval resume preserves the current count.
- A new unrelated logical execution starts at zero.
- The configured maximum is enforced before another agent LLM invocation. Phase 4.1 specifies a default maximum of five; the limit is configuration, not another AgentState field.
- Background memory summarization is not counted as an agent iteration.

## 8. Execution status and invariants

The allowed values are:

- `running`
- `waiting_for_clarification`
- `waiting_for_approval`
- `completed`
- `failed`

Required invariants:

1. `pending_approval` and `pending_clarification` cannot both be active.
2. `waiting_for_approval` requires `pending_approval` and no pending clarification.
3. `waiting_for_clarification` requires `pending_clarification` and no pending approval.
4. `running` has no unresolved interaction object after the corresponding interaction has been accepted and cleared.
5. `completed` and `failed` are terminal for that logical execution and must not retain an actionable pending interaction.
6. SQLite is authoritative for durable application execution status. `AgentState.execution_status` is runtime state; the checkpointer is the graph snapshot. API responses must report the durable status.
7. Because SQLite writes and checkpoint writes are not one atomic transaction, initialization and resumption must reconcile the durable execution record with the checkpoint and return a controlled recovery error when they are inconsistent.

## 9. Field ownership and update rules

| Field | Authorized writer(s) | Update rule |
|---|---|---|
| `execution_id` | New-execution initializer and recovery path | Generate for a new logical request; preserve for clarification continuation and approval resume |
| `messages` | Context initializer, agent node, tool executor/result handler, interaction handlers | Use message IDs and the reducer consistently; tool messages must match tool-call IDs; replace bounded context only through an explicit safe operation |
| `memory_summary` | Context initializer | Load the latest durable summary at execution start; background summarization updates SQLite, not an arbitrary in-flight graph state |
| `iteration_count` | Agent invocation boundary | Increment exactly once immediately before each LLM attempt |
| `execution_status` | Execution lifecycle controller and recovery path | Change only at defined lifecycle transitions and keep durable SQLite status synchronized |
| `pending_approval` | Approval handler and approval-resolution path | Set when a validated deletion request enters approval; clear only after a recorded decision or controlled cancellation/recovery |
| `pending_clarification` | Agent/clarification handling and context initialization | Set when clarification is requested; carry into the next invocation; clear when answered or superseded |

Other nodes may read state fields but must not mutate fields outside their responsibility. Multiple authorized writers to `messages` are permitted, provided they follow the same reducer and message-correlation contract.

## 10. Initialization and resumption

### New logical request

1. Validate the `thread_id` against the durable conversation record.
2. Determine whether the incoming message answers an outstanding clarification. If yes, retain its `execution_id`; otherwise create a new one.
3. Load the latest durable memory summary and the bounded recent message window.
4. Insert the incoming user message idempotently into durable history and runtime context.
5. Initialize execution fields (`iteration_count`, status, and pending interaction fields) without overwriting unrelated conversation identity.
6. Invoke the graph using the existing `thread_id` checkpoint namespace.
7. Ensure stale runtime messages are replaced/trimmed safely rather than appended indefinitely.

### Approval resume

1. Validate `thread_id` and `approval_id` against the durable pending approval record.
2. Confirm that the durable execution is waiting for the matching approval and that its checkpoint exists.
3. Resume the existing interrupted graph execution; do not initialize a new execution or rebuild its state as a fresh turn.
4. Preserve `execution_id`, `iteration_count`, and the pending approval context until the approval handler records and applies the decision.
5. Prevent duplicate deletion through the database-authoritative execution ledger and idempotency checks.

### Clarification continuation

1. The previous graph invocation has ended normally; there is no suspended graph task to resume.
2. Validate the same conversation thread and load the persisted clarification context.
3. Start a new graph invocation using the same logical `execution_id` if the new message answers that clarification.
4. Load/rehydrate the bounded message window without duplicating existing messages.
5. Clear the pending clarification only when it has been resolved or superseded.

## 11. Runtime validation

Use targeted validation at critical boundaries rather than validating the entire state after every node:

- New execution initialization.
- Approval resume and clarification continuation.
- Creation and resolution of pending interactions.
- Execution status transitions and invariants.
- Immediately before an agent LLM call (including iteration-limit enforcement).
- Final completion/failure.

TypedDict defines the graph state shape; it does not provide runtime validation. Use focused Pydantic validation for interaction payloads and critical boundary checks. Unit and integration tests remain necessary.

## 12. Explicit exclusions

The following are intentionally not AgentState fields:

- `thread_id` — LangGraph config.
- `request_id` — API request scope.
- `current_user_message` — represented as a `HumanMessage` in `messages`.
- `tool_calls` / `tool_results` — represented by `AIMessage` and `ToolMessage` pairs.
- `conversation_history` — durable SQLite history; only a bounded window is loaded into state.
- `max_iterations` — configuration, not mutable execution state.
- Database task objects, approval history, deletion ledger rows, and summary-job records — durable application data.

## 13. Implementation prerequisites discovered in the supplied archive

The supplied archive does not yet contain a graph implementation or AgentState module. `app/agent/` and `app/llm/` contain only empty package initializers. `langgraph` is absent from both `pyproject.toml` and `uv.lock`, even though Phase 4 requires LangGraph. Existing Gemma integration tests invoke the model and tools directly; they do not test graph behavior.

Source inspection also found a deletion-flow gap that must not be hidden by the graph implementation: the current `delete_task` tool only verifies that a task exists and returns a `pending_approval` response. It does not create a durable deletion-request record or an `approval_id` / `deletion_request_id`. Phase 4.2 requires those durable records before an approval interrupt can safely be implemented. The graph must not invent those identifiers or treat the current tool response as a persisted approval request.

The implementation environment used for this inspection is Python 3.13.5, while this project explicitly requires Python 3.12. An attempt to provision Python 3.12 failed because the runtime could not reach the package host. LangGraph is also not installed in the inspection environment. Therefore no LangGraph API behavior or graph test has been claimed as verified.

Before graph implementation, add and lock LangGraph and its SQLite checkpointer dependency in the project's Python 3.12 environment. Implement against those resolved versions, and test the reducer/message replacement behavior rather than assuming it. Implement the durable deletion-request and idempotent execution records required by Phase 4.2 before connecting the approval path.

---

**Freeze basis:** the seven-field state inventory, TypedDict choice, message reducer, identity boundaries, iteration semantics, lifecycle statuses, separate pending interactions, SQLite authority, targeted validation, and field ownership policy follow the previously established Stage 2 decisions. The clarification-vs-approval distinction follows the approved Phase 4 graph architecture.
