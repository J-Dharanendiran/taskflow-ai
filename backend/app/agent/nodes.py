
"""LangGraph Agent node for TaskFlow AI."""

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.state import AgentState
from app.agent.validators import validate_agent_state
from app.llm.factory import create_chat_model
from app.tools.task_tools import TASK_TOOLS

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 5

CLARIFICATION_PREFIX = "<taskflow_clarification>"
CLARIFICATION_SUFFIX = "</taskflow_clarification>"
UNSUPPORTED_PREFIX = "<taskflow_unsupported>"
UNSUPPORTED_SUFFIX = "</taskflow_unsupported>"

VALID_CLARIFICATION_REASONS = {
    "missing_information",
    "ambiguous_reference",
    "unsupported_value",
}

SYSTEM_PROMPT = f"""
You are TaskFlow AI, a task management assistant.

Your responsibilities:
- Help users create, list, update, complete, reopen, and request deletion of tasks.
- Use the available tools for task operations.
- Never invent task IDs or task information.
- Ask for clarification when required information is missing,
  ambiguous, or unsupported.
- Supported task priorities are low, medium, and high.
- Never silently replace an unsupported value.
- Explain tool failures accurately.
- Never claim an operation succeeded unless its result confirms success.
- Deletion requires explicit human approval. Requesting deletion does
  not mean the task has been deleted.
- Do not call tools for general informational questions.

Response protocol:
1. For task operations, use the available tools.
2. When clarification is required, respond ONLY in this format:
   {CLARIFICATION_PREFIX}
   {{"reason":"missing_information","question":"Your question"}}
   {CLARIFICATION_SUFFIX}

   Allowed reasons:
   - missing_information
   - ambiguous_reference
   - unsupported_value

3. When a request is outside your supported capabilities, respond ONLY
   in this format:
   {UNSUPPORTED_PREFIX}A concise explanation.{UNSUPPORTED_SUFFIX}

4. For ordinary answers and completed requests, respond with plain text.
5. Never include these control markers in ordinary user-facing responses.

Keep responses clear and concise.
"""


def _parse_clarification(content: str) -> dict:
    """Validate and extract a structured clarification response."""

    if not content.startswith(CLARIFICATION_PREFIX):
        raise ValueError("Invalid clarification response prefix.")

    if not content.endswith(CLARIFICATION_SUFFIX):
        raise ValueError("Invalid clarification response suffix.")

    payload = content[
        len(CLARIFICATION_PREFIX):-len(CLARIFICATION_SUFFIX)
    ].strip()

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("Invalid clarification response JSON.") from error

    if not isinstance(data, dict):
        raise ValueError("Clarification response must be a JSON object.")

    if set(data) != {"reason", "question"}:
        raise ValueError(
            "Clarification response must contain exactly 'reason' and 'question'."
        )

    reason = data["reason"]
    question = data["question"]

    if reason not in VALID_CLARIFICATION_REASONS:
        raise ValueError("Invalid clarification reason.")

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Clarification question must be non-empty.")

    return {
        "reason": reason,
        "question": question.strip(),
    }


def _parse_unsupported(content: str) -> str:
    """Extract an unsupported-request explanation."""

    if not content.startswith(UNSUPPORTED_PREFIX):
        raise ValueError("Invalid unsupported response prefix.")

    if not content.endswith(UNSUPPORTED_SUFFIX):
        raise ValueError("Invalid unsupported response suffix.")

    explanation = content[
        len(UNSUPPORTED_PREFIX):-len(UNSUPPORTED_SUFFIX)
    ].strip()

    if not explanation:
        raise ValueError("Unsupported-request explanation must be non-empty.")

    return explanation


async def agent_node(
    state: AgentState,
    config: RunnableConfig,
) -> dict:
    """Invoke Gemma and classify its response."""

    validate_agent_state(state)

    # Stop before making another LLM invocation.
    if state["iteration_count"] >= MAX_AGENT_ITERATIONS:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "I've reached the maximum number of processing steps "
                        "for this request. Please try a more specific request."
                    )
                )
            ],
            "execution_status": "completed",
        }

    system_content = SYSTEM_PROMPT

    if state["memory_summary"]:
        system_content += (
            "\n\nRelevant conversation context:\n"
            f"{state['memory_summary']}"
        )

    messages = [
        SystemMessage(content=system_content),
        *state["messages"],
    ]

    llm = create_chat_model()
    llm_with_tools = llm.bind_tools(TASK_TOOLS)

    # Every invocation attempt counts, including failed attempts.
    iteration_count = state["iteration_count"] + 1

    try:
        response = await llm_with_tools.ainvoke(
            messages,
            config=config,
        )
    except Exception:
        logger.exception(
            "Agent LLM invocation failed for execution %s",
            state["execution_id"],
        )
        return {
            "messages": [
                AIMessage(
                    content=(
                        "I couldn't process your request because the language "
                        "model encountered an error. Please try again."
                    )
                )
            ],
            "iteration_count": iteration_count,
            "execution_status": "failed",
        }

    if not isinstance(response, AIMessage):
        raise TypeError("The Agent must return an AIMessage.")

    updated_state = {
        "messages": [response],
        "iteration_count": iteration_count,
    }

    # Outcome 1: Tool calls.
    if response.tool_calls:
        return updated_state

    if not isinstance(response.content, str):
        raise ValueError("Agent response content must be text.")

    content = response.content.strip()

    # Outcome 2: Clarification required.
    if content.startswith(CLARIFICATION_PREFIX):
        clarification = _parse_clarification(content)

        original_message = next(
            (
                message
                for message in reversed(state["messages"])
                if isinstance(message, HumanMessage)
            ),
            None,
        )

        if original_message is None or not original_message.id:
            raise ValueError(
                "A message ID is required to create pending clarification."
            )

        updated_state["messages"] = [
            response.model_copy(update={"content": clarification["question"]})
        ]
        updated_state["pending_clarification"] = {
            "question": clarification["question"],
            "reason": clarification["reason"],
            "original_message_id": original_message.id,
        }
        updated_state["execution_status"] = "waiting_for_clarification"

        return updated_state

    # Outcome 3: Unsupported request.
    if content.startswith(UNSUPPORTED_PREFIX):
        explanation = _parse_unsupported(content)

        updated_state["messages"] = [
            response.model_copy(update={"content": explanation})
        ]
        updated_state["execution_status"] = "completed"

        return updated_state

    # Outcome 4: Ordinary final response.
    updated_state["execution_status"] = "completed"

    return updated_state
