import json
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from .prompt import ILLUSTRATOR_DESCRIPTION, ILLUSTRATOR_PROMPT
from .tools import generate_images, generate_page_image
from pydantic import BaseModel, Field
from typing import Any, List, Literal, Optional

MODEL = LiteLlm(model="openai/gpt-4o-mini")

_GENERATION_TOOL_NAMES = {"generate_images", "generate_page_image"}

def gate_illustrator_generation(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> Optional[dict]:
    """Serializes generate_images/generate_page_image so they never run concurrently.

    Status stays GENERATING while any of the 5 pages are still missing, so
    sequential page-by-page calls (and retries) within one invocation keep
    working. Once all 5 pages exist, status settles into PENDING_REVIEW: a
    call in the SAME invocation is blocked (no self-triggered regeneration),
    but a call in a NEW invocation is allowed — this only happens after the
    orchestrator re-invokes this agent following a real user reply asking
    for a specific page to be redone.
    """
    if tool.name not in _GENERATION_TOOL_NAMES:
        return None

    status = tool_context.state.get("illustrator_generation_status")
    if status == "GENERATING":
        return {
            "status": "blocked",
            "message": "이미 다른 이미지 생성 작업이 진행 중입니다. 완료될 때까지 기다려주세요.",
        }
    if status == "PENDING_REVIEW":
        last_invocation_id = tool_context.state.get("illustrator_generation_invocation_id")
        if last_invocation_id == tool_context.invocation_id:
            return {
                "status": "blocked",
                "message": "이미 이번 턴에 5페이지 생성이 완료되었습니다. 사용자 확인을 먼저 받아야 합니다.",
            }

    tool_context.state["illustrator_generation_status"] = "GENERATING"
    return None

def attach_illustrator_image_paths(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    """Overwrites image_url_or_path with the real saved paths (tracked in state
    as pages were generated) and re-emits the corrected JSON as this agent's
    final response, so neither session state nor what the orchestrator/user
    sees can ever reflect a path the LLM invented or mistranslated."""
    output = callback_context.state.get("illustrator_output")
    if not output:
        return None

    page_paths = callback_context.state.get("illustrator_page_paths", {})
    for page in output.get("pages", []):
        real_path = page_paths.get(page.get("page_number"))
        if real_path is not None:
            page["image_url_or_path"] = real_path

    callback_context.state["illustrator_output"] = output
    return types.Content(
        role="model",
        parts=[types.Part.from_text(text=json.dumps(output, ensure_ascii=False))],
    )

class IllustratorPageOutput(BaseModel):
    page_number: int = Field(description="Page number (1–5)")
    image_prompt: str = Field(description="Final image generation prompt. (background, action, composition, lighting, mood)")
    filename: str = Field(description="name of the generated image for this page")

class IllustratorOutput(BaseModel):
    pages: List[IllustratorPageOutput] = Field(
        description="List of exactly 5 pages, each containing the image prompt and the resulting image URL or path"
    )
    status: Literal["pending_review", "confirmed"] = Field(description="'pending_review' until the real user has explicitly approved these 5 pages in a prior conversation turn; 'confirmed' only after that approval")

illustrator_agent = Agent(
    name="IllustratorAgent",
    description=ILLUSTRATOR_DESCRIPTION,
    instruction=ILLUSTRATOR_PROMPT,
    model=MODEL,
    output_schema=IllustratorOutput,
    output_key="illustrator_output",
    tools=[
        generate_images,
        generate_page_image,
    ],
    before_tool_callback=gate_illustrator_generation,
    after_agent_callback=attach_illustrator_image_paths,
)