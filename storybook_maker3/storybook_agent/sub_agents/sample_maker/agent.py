from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from .prompt import SAMPLE_MAKER_DESCRIPTION, SAMPLE_MAKER_PROMPT
from .tools import generate_sample_image
from pydantic import BaseModel, Field
from typing import Any, Literal, Optional

MODEL = LiteLlm(model="openai/gpt-4o-mini")

def gate_sample_generation(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> Optional[dict]:
    """Blocks duplicate generate_sample_image calls within the same review cycle.

    A sample stays PENDING_REVIEW until a new invocation (i.e. the orchestrator
    re-invoked this agent after getting a real user reply) calls the tool again,
    which is treated as the user having asked for a regeneration.
    """
    if tool.name != "generate_sample_image":
        return None

    status = tool_context.state.get("sample_generation_status")
    last_invocation_id = tool_context.state.get("sample_generation_invocation_id")

    if status == "GENERATING":
        return {
            "status": "blocked",
            "message": "이미 샘플 이미지를 생성하는 중입니다. 완료될 때까지 기다려주세요.",
        }
    if status == "PENDING_REVIEW" and last_invocation_id == tool_context.invocation_id:
        return {
            "status": "blocked",
            "message": "이미 이번 턴에 샘플을 생성했습니다. 사용자 확인을 먼저 받아야 합니다.",
        }

    tool_context.state["sample_generation_status"] = "GENERATING"
    tool_context.state["sample_generation_invocation_id"] = tool_context.invocation_id
    return None

class IllustratorConceptOutput(BaseModel):
    art_style_guide: str = Field(description="Visual style applied consistently across all 5 pages (e.g. watercolor, pastel tones, soft line art, warm picture-book palette)")
    character_sheet: str = Field(description="Fixed visual description of the protagonist used in every image prompt to maintain character consistency (hair/fur, eyes, outfit, body type, props)")
    sample_image_url_or_path: str = Field(description="generated sample image path, regardless of confirmation status")
    status: Literal["pending_review", "confirmed"] = Field(description="'pending_review' until the real user has explicitly approved this sample in a prior conversation turn; 'confirmed' only after that approval")

sample_maker_agent = Agent(
    name="SampleMakerAgent",
    description=SAMPLE_MAKER_DESCRIPTION,
    instruction=SAMPLE_MAKER_PROMPT,
    model=MODEL,
    output_schema=IllustratorConceptOutput,
    output_key="illustrator_concept_output",
    tools=[
        generate_sample_image,
    ],
    before_tool_callback=gate_sample_generation,
)