import base64
import os
import re
from openai import OpenAI
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from storybook_agent.image_utils import local_path, save_local, save_artifact
from typing import Any, Optional

client = OpenAI()


def _mark_pages_generated(tool_context: ToolContext, page_paths: dict) -> None:
    """Tracks each page's real saved path and only locks out further generation
    once every actual required page_number has been generated (set-based check,
    not a raw count, so a stray/duplicate/invalid page_number can't fake completion).
    `page_paths` is authoritative for image_url_or_path — the LLM's own final
    JSON text is never trusted for this."""
    story_writer_output = tool_context.state.get("story_writer_output", {})
    required_pages = {p.get("page_number") for p in story_writer_output.get("pages", [])}

    all_page_paths = dict(tool_context.state.get("illustrator_page_paths", {}))
    all_page_paths.update(page_paths)
    tool_context.state["illustrator_page_paths"] = all_page_paths

    done_pages = set(all_page_paths.keys())

    if required_pages and required_pages.issubset(done_pages):
        tool_context.state["illustrator_generation_status"] = "PENDING_REVIEW"
        tool_context.state["illustrator_generation_invocation_id"] = tool_context.invocation_id
    else:
        tool_context.state["illustrator_generation_status"] = None


def make_gate_generate_page_image(page_number: int):
    """Blocks duplicate generate_page_image calls for this page within the
    same turn: one while this page is actively generating, and one more if
    this page already finished generating in this exact invocation. A new
    invocation (e.g. the user asking for a redo) is still allowed through."""

    def gate_generate_page_image(
        tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
    ) -> Optional[dict]:
        status_key = f"page{page_number}_call_status"
        invocation_key = f"page{page_number}_call_invocation_id"

        status = tool_context.state.get(status_key)
        last_invocation_id = tool_context.state.get(invocation_key)

        if status == "GENERATING":
            return {
                "status": "blocked",
                "message": f"이미 {page_number}페이지 이미지를 생성하는 중입니다. 완료될 때까지 기다려주세요.",
            }
        if status == "DONE" and last_invocation_id == tool_context.invocation_id:
            return {
                "status": "blocked",
                "message": f"이미 이번 턴에 {page_number}페이지 이미지를 생성했습니다.",
            }

        tool_context.state[status_key] = "GENERATING"
        tool_context.state[invocation_key] = tool_context.invocation_id
        return None

    return gate_generate_page_image


def make_generate_page_image(page_number: int):
    """Builds a page-image tool with page_number fixed by closure, so the
    agent it's attached to can only ever generate that one page — the LLM
    never supplies page_number and can't call it for a different page."""

    async def generate_page_image(
        tool_context: ToolContext,
    ) -> dict:
        """Regenerate this agent's fixed page image with an additional correction prompt appended to the illustration description."""
        attempts = tool_context.state.get("sample_attempts", 0) + 1
        tool_context.state["sample_attempts"] = attempts

        story_writer_output = tool_context.state.get("story_writer_output")
        illustrator_concept_output = tool_context.state.get("illustrator_concept_output")
        art_style_guide = illustrator_concept_output.get("art_style_guide")
        character_sheet = illustrator_concept_output.get("character_sheet")
        pages = story_writer_output.get("pages")
        title = story_writer_output.get("title")

        safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_")[:7]

        page = next((p for p in pages if p.get("page_number") == page_number), None)
        if page is None:
            tool_context.state["illustrator_generation_status"] = None
            tool_context.state[f"page{page_number}_call_status"] = None
            return {"error": f"page_number {page_number} not found"}

        illustration_description = page.get("illustration_description", "")
        enhanced_prompt = art_style_guide + ', ' + character_sheet + ', ' + illustration_description

        filename = f"{attempts}_{safe_title}_page_{page_number}_image.jpeg"

        image = client.images.generate(
            model="gpt-image-1",
            prompt=enhanced_prompt,
            n=1,
            quality="low",
            moderation="low",
            output_format="jpeg",
            background="opaque",
            size="1024x1024",
        )

        image_bytes = base64.b64decode(image.data[0].b64_json)

        await save_artifact(tool_context, filename, image_bytes)
        path = save_local(filename, image_bytes)

        _mark_pages_generated(tool_context, {page_number: filename})
        tool_context.state[f"page{page_number}_call_status"] = "DONE"

        return {
            "page_number": page_number,
            "filename": filename,
        }

    return generate_page_image
