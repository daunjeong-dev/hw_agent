"""Shared ADK callbacks that surface agent/tool execution info in adk web's
Trace tab, by attaching attributes to the current OpenTelemetry span.

ADK already wraps each agent run (before_agent_callback -> _run_async_impl ->
after_agent_callback) in a single `invoke_agent` span, and each tool call in a
single `execute_tool` span, so before/after callbacks for the same
agent/tool execution share one span. Writing "start"/"end" info under two
distinct attribute keys (rather than reusing one key) keeps both visible
instead of the later write overwriting the earlier one.
"""

import json
from typing import Any, Callable, Optional, Tuple

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from opentelemetry import trace


def log_agent_start(callback_context: CallbackContext) -> None:
    span = trace.get_current_span()
    span.set_attribute("app.log.agent_name", callback_context.agent_name)
    span.set_attribute("app.log.invocation_id", callback_context.invocation_id)
    return None


def log_tool_start(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> Optional[dict]:
    span = trace.get_current_span()
    span.set_attribute("app.log.tool_name", tool.name)
    span.set_attribute("app.log.tool_agent_name", tool_context.agent_name)
    span.set_attribute("app.log.tool_args", json.dumps(args, default=str))
    return None


def make_agent_lifecycle_logger(
    start_message: str, end_message: str
) -> Tuple[
    Callable[[CallbackContext], Optional[types.Content]],
    Callable[[CallbackContext], Optional[types.Content]],
]:
    """Returns (before_agent_callback, after_agent_callback) that surface
    end_message as a chat event.

    `after` simply returns Content: _handle_after_agent_callback wraps that in
    an Event and yields it once _run_async_impl has already finished, so it's
    a pure addition with nothing left to short-circuit.

    `before` can't do the same — _handle_before_agent_callback treats any
    truthy return as an override and force-sets ctx.end_invocation = True,
    which skips the agent's actual run entirely (see base_agent.py:497-506),
    cancelling its tool calls. So `before` always returns None here (no
    start_message shown in chat) rather than risk that.
    """

    def before(callback_context: CallbackContext) -> None:
        return None

    def after(callback_context: CallbackContext) -> Optional[types.Content]:
        return types.Content(role="model", parts=[types.Part(text=end_message)])

    return before, after
