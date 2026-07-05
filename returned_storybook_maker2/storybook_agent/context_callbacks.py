"""Shared before_model_callback that caps how much conversation history each
LlmAgent call resends to the model.

ADK's default include_contents behavior resends the *entire* session history
on every single LLM call. In this pipeline that means every stage after the
first (SampleMaker, Illustrator, each Page{N}GeneratorAgent, ...) resends all
prior stages' full output_schema JSON plus every retry-loop tool
message, so the context keeps growing across the run until a late-stage call
(commonly IllustratorAgent's retry loop or a Page{N}GeneratorAgent) blows past
the model's TPM limit. Trimming only needs to happen right before each LLM
call, not once at the end of the run — by then the failing call has already
been sent.
"""

from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.genai import types

# Number of oldest contents always kept as-is (anchors the original task/user
# request so agents don't lose the original ask across trims).
HEAD_KEEP = 2

# Rough budget for the kept tail, in characters (~3 chars/token for mixed
# Korean/English text). Deliberately well under the 200k TPM limit so it
# still leaves headroom for the system instruction, tool schemas, and the
# model's own response tokens.
MAX_TAIL_CHARS = 120_000

_OMISSION_NOTICE = "(...이전 대화 일부가 길어서 생략되었습니다...)"


def _content_char_len(content: types.Content) -> int:
    total = 0
    for part in content.parts or []:
        if part.text:
            total += len(part.text)
        elif part.function_call:
            total += len(part.function_call.name or "") + len(str(part.function_call.args or ""))
        elif part.function_response:
            total += len(str(part.function_response.response))
    return total


def _has_function_response(content: types.Content) -> bool:
    return any(part.function_response for part in (content.parts or []))


def trim_context(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """Keeps the first HEAD_KEEP contents plus a char-budgeted window of the
    most recent contents, dropping whatever falls in between.

    Walks the tail backwards from the most recent content so it always keeps
    "the latest N chars worth" rather than an arbitrary item count, since a
    single retry-loop tool response can be far larger than a short chat
    turn. If the resulting cut would orphan a function_response from its
    matching function_call (which must stay adjacent for the model API),
    the cut point is pulled back to include that pairing.
    """
    contents = llm_request.contents
    if len(contents) <= HEAD_KEEP:
        return None

    head = contents[:HEAD_KEEP]
    tail_pool = contents[HEAD_KEEP:]

    kept_tail: list[types.Content] = []
    running_chars = 0
    cut_index = len(contents)
    for content in reversed(tail_pool):
        running_chars += _content_char_len(content)
        kept_tail.append(content)
        cut_index -= 1
        if running_chars >= MAX_TAIL_CHARS:
            break
    kept_tail.reverse()

    if cut_index <= HEAD_KEEP:
        return None  # everything already fits within budget; nothing to trim

    while kept_tail and _has_function_response(kept_tail[0]) and cut_index > HEAD_KEEP:
        cut_index -= 1
        kept_tail.insert(0, contents[cut_index])

    marker = types.Content(role="user", parts=[types.Part(text=_OMISSION_NOTICE)])
    llm_request.contents = head + [marker] + kept_tail
    return None
