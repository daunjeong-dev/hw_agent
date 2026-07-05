import json
from google.adk.agents import Agent, ParallelAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from .prompt import ILLUSTRATOR_DESCRIPTION, ILLUSTRATOR_PROMPT
from .image_generator.agent import parallel_image_generator
from ...telemetry_callbacks import log_tool_start, make_agent_lifecycle_logger
from ...context_callbacks import trim_context
from pydantic import BaseModel, Field
from typing import Any, List, Literal, Optional

# MODEL = LiteLlm(model="openai/gpt-4o-mini", parallel_tool_calls=False)
MODEL = LiteLlm(model="openai/gpt-4o", parallel_tool_calls=False)

class IllustratorPageOutput(BaseModel):
    page_number: int = Field(description="Page number (1–5)")
    text: str = Field(description="Final storybook text")
    filename: str = Field(description="name of the generated image for this page")

class IllustratorOutput(BaseModel):
    title: str = Field(description="storybook title")
    pages: List[IllustratorPageOutput] = Field(
        description="List of exactly 5 pages, each containing the text and the resulting image filename"
    )


def gate_illustration_generation(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> Optional[dict]:
    """Blocks duplicate AgentTool(parallel_image_generator) calls within the same review cycle.

    Uses a dedicated state key rather than illustrator_generation_status, since
    image_generator/tools.py resets that key to None after every single page
    completion until all 5 are done, which would otherwise reopen this gate
    mid-flight.
    """
    if tool.name != parallel_image_generator.name:
        return None

    status = tool_context.state.get("illustration_call_status")
    last_invocation_id = tool_context.state.get("illustration_call_invocation_id")

    if status == "GENERATING":
        story_writer_output = tool_context.state.get("story_writer_output", {})
        total_pages = len(story_writer_output.get("pages", []))
        pages = _all_page_results(tool_context)
        return {
            "status": "in_progress",
            "pages": pages,
            "message": (
                f"아직 삽화 생성이 끝나지 않았습니다 ({len(pages)}/{total_pages} 페이지 완료). "
                "최종 출력을 작성하지 말고, 이 결과를 참고해 기다렸다가 다시 확인하세요."
            ),
        }
    if status == "PENDING_REVIEW" and last_invocation_id == tool_context.invocation_id:
        return {
            "status": "done",
            "pages": _all_page_results(tool_context),
            "message": "이미 모든 페이지의 삽화가 생성되었습니다. 이 결과로 최종 스토리북을 보여주세요.",
        }

    tool_context.state["illustration_call_status"] = "GENERATING"
    tool_context.state["illustration_call_invocation_id"] = tool_context.invocation_id
    return None


def _all_page_results(tool_context: ToolContext) -> list[dict]:
    page_paths = tool_context.state.get("illustrator_page_paths", {})
    return [
        {"page_number": page_number, "filename": filename}
        for page_number, filename in sorted(page_paths.items(), key=lambda item: int(item[0]))
    ]


def mark_illustration_call_done(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext, tool_response: dict
) -> Optional[dict]:
    """Overrides the AgentTool's raw response with the full set of page results.

    ParallelAgent runs the 5 page generators concurrently, so AgentTool only
    surfaces whichever sub-agent's event happened to arrive last — the model
    would otherwise see just one page's filename instead of all 5, and either
    hallucinate the rest or re-call the tool looking for them.

    Only marks the call PENDING_REVIEW once every required page is actually
    present in illustrator_page_paths; otherwise resets the gate so the next
    call can resume generating the missing pages, instead of locking in a
    premature "done" over a partial page set (which previously caused the
    gate to keep replaying that same partial result forever).
    """
    if tool.name != parallel_image_generator.name:
        return None

    story_writer_output = tool_context.state.get("story_writer_output", {})
    required_pages = {p.get("page_number") for p in story_writer_output.get("pages", [])}
    pages = _all_page_results(tool_context)
    done_pages = {page["page_number"] for page in pages}

    if required_pages and required_pages.issubset(done_pages):
        tool_context.state["illustration_call_status"] = "PENDING_REVIEW"
        return {
            "status": "done",
            "pages": pages,
            "message": "모든 페이지의 삽화가 생성되었습니다. 이 결과로 최종 출력을 작성하세요.",
        }

    tool_context.state["illustration_call_status"] = None
    return {
        "status": "in_progress",
        "pages": pages,
        "message": (
            f"아직 삽화 생성이 끝나지 않았습니다 ({len(done_pages)}/{len(required_pages)} 페이지 완료). "
            "최종 출력을 작성하지 말고 이 도구를 다시 호출해 나머지 페이지를 완성하세요."
        ),
    }


def fix_illustrator_output(callback_context: CallbackContext) -> None:
    """Overwrites each page's filename with the tool's authoritative value,
    since the LLM's own final JSON (output_schema) can hallucinate filenames
    for pages it never actually saw in the tool response (see
    mark_illustration_call_done)."""
    page_paths = callback_context.state.get("illustrator_page_paths", {})
    output = callback_context.state.get("illustrator_output")
    if not output or not page_paths:
        return None
    for page in output.get("pages", []):
        filename = page_paths.get(page.get("page_number"))
        if filename is not None:
            page["filename"] = filename
    callback_context.state["illustrator_output"] = output
    return None


_illustrator_before, _illustrator_after = make_agent_lifecycle_logger(
    "삽화 생성 시작", "삽화 생성 종료"
)

illustrator_agent = Agent(
    name="IllustratorAgent",
    description=ILLUSTRATOR_DESCRIPTION,
    instruction=ILLUSTRATOR_PROMPT,
    model=MODEL,
    output_schema=IllustratorOutput,
    output_key="illustrator_output",
    tools=[
        AgentTool(parallel_image_generator),
    ],
    before_agent_callback=_illustrator_before,
    after_agent_callback=[fix_illustrator_output],
    before_tool_callback=[gate_illustration_generation, log_tool_start],
    after_tool_callback=mark_illustration_call_done,
    before_model_callback=trim_context,
)