from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from .prompt import DISPLAY_DESCRIPTION, DISPLAY_PROMPT
from .tools import build_illustrated_content, render_storybook_markdown
from ...telemetry_callbacks import log_tool_start, make_agent_lifecycle_logger
from ...context_callbacks import trim_context

MODEL = LiteLlm(model="openai/gpt-4o-mini", parallel_tool_calls=False)

_display_before, _display_after = make_agent_lifecycle_logger(
    "그림책 MD 출력 시작", "그림책 MD 출력 완료"
)


def _after_display_agent(callback_context: CallbackContext) -> types.Content:
    """Appends the illustrated storybook as one extra event after the
    agent's own reply.

    ADK's after_agent_callback list stops at the first callback that returns
    non-None (base_agent.py _handle_after_agent_callback), and _display_after
    always returns a Content — so this can't be listed alongside it; it has
    to be the sole after_agent_callback.
    """
    illustrated_content = build_illustrated_content(callback_context)
    if illustrated_content is None:
        return None
    return types.Content(
        role="model",
        parts=list(illustrated_content.parts),
    )


display_agent = Agent(
    name="DisplayAgent",
    description=DISPLAY_DESCRIPTION,
    instruction=DISPLAY_PROMPT,
    model=MODEL,
    tools=[render_storybook_markdown],
    before_agent_callback=_display_before,
    after_agent_callback=_after_display_agent,
    before_tool_callback=log_tool_start,
    before_model_callback=trim_context,
)
