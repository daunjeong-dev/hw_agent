from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from .prompt import STORY_WRITER_DESCRIPTION, STORY_WRITER_PROMPT
from pydantic import BaseModel, Field
from typing import List


class PageOutput(BaseModel):
    page_number: int = Field(description="Page number (1–5)")
    stage: str = Field(description="Narrative stage of this page (e.g. introduction, conflict, climax, resolution, epilogue)")
    content_summary: str = Field(
        description="Brief summary of the story event or role this page plays in the overall narrative"
    )
    text: str = Field(
        description="Actual storybook text to be printed on the page (1–2 child-friendly sentences)"
    )
    illustration_description: str = Field(
        description="Detailed scene description for image generation: character actions, background, mood, and key objects"
    )


class StoryWriterOutput(BaseModel):
    title: str = Field(description="Title of the storybook")
    theme: str = Field(description="Core message or moral of the story in one sentence")
    synopsis: str = Field(description="3–5 sentence summary of the overall plot")
    planning_notes: str = Field(description="Editorial notes covering tone, target age group, and distinguishing features of this storybook")
    protagonist_visual_guide: str = Field(description="Fixed visual traits of the protagonist (hair/fur color, eye color, outfit, body type, distinctive props) to ensure consistency across all 5 pages")
    pages: List[PageOutput] = Field(
        description="List of exactly 5 pages comprising the full storybook"
    )


MODEL = LiteLlm(model="openai/gpt-4o-mini")

story_writer_agent = Agent(
    name="StoryWriterAgent",
    description=STORY_WRITER_DESCRIPTION,
    instruction=STORY_WRITER_PROMPT,
    model=MODEL,
    output_schema=StoryWriterOutput,
    output_key="story_writer_output",
)
