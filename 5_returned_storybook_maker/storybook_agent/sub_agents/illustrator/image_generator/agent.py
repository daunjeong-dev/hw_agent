import json
from google.adk.agents import Agent, ParallelAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from .prompt import IMAGEGENERATOR_DESCRIPTION, IMAGEGENERATOR_PROMPT, PARALLEL_GENERATOR_DESCRIPTION
from .tools import make_generate_page_image, make_gate_generate_page_image
from ....telemetry_callbacks import log_tool_start, make_agent_lifecycle_logger
from ....context_callbacks import trim_context
from pydantic import BaseModel, Field
from typing import Any, List, Literal, Optional

MODEL = LiteLlm(model="openai/gpt-4o-mini", parallel_tool_calls=False)

class ImageGeneratorOutput(BaseModel):
    page_number: int = Field(description="Page number (1–5)")
    filename: str = Field(description="name of the generated image for this page")


def make_fix_page_output(page_number: int):
    """Overwrites this agent's output_key state with the tool's authoritative
    page_number/filename after the agent turn finishes, since the LLM's own
    final JSON (output_schema) can hallucinate the wrong page_number/filename
    instead of reporting what the tool actually returned."""

    def fix_page_output(callback_context: CallbackContext) -> None:
        page_paths = callback_context.state.get("illustrator_page_paths", {})
        filename = page_paths.get(page_number)
        if filename is None:
            return None
        callback_context.state[f"page{page_number}_output"] = {
            "page_number": page_number,
            "filename": filename,
        }
        return None

    return fix_page_output


def make_page_generator(page_number: int) -> Agent:
    page_before, page_after = make_agent_lifecycle_logger(
        f"{page_number}페이지 생성 시작", f"{page_number}페이지 생성 종료"
    )
    return Agent(
        name=f"Page{page_number}GeneratorAgent",
        description=IMAGEGENERATOR_DESCRIPTION,
        instruction=IMAGEGENERATOR_PROMPT,
        model=MODEL,
        output_schema=ImageGeneratorOutput,
        output_key=f"page{page_number}_output",
        tools=[
            make_generate_page_image(page_number),
        ],
        before_agent_callback=page_before,
        after_agent_callback=[make_fix_page_output(page_number)],
        before_tool_callback=[
            make_gate_generate_page_image(page_number),
            log_tool_start,
        ],
        before_model_callback=trim_context,
    )


page1_generator = make_page_generator(1)
page2_generator = make_page_generator(2)
page3_generator = make_page_generator(3)
page4_generator = make_page_generator(4)
page5_generator = make_page_generator(5)

parallel_image_generator = ParallelAgent(
    name="ParallelImageGeneratorAgent",
    description=PARALLEL_GENERATOR_DESCRIPTION,
    sub_agents=[
        page1_generator,
        page2_generator,
        page3_generator,
        page4_generator,
        page5_generator,
    ],
)