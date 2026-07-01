import base64
import os
import re
from openai import OpenAI
from google.adk.tools.tool_context import ToolContext
from storybook_agent.image_utils import local_path, save_local, save_artifact

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


async def generate_images(tool_context: ToolContext):
    attempts = tool_context.state.get("sample_attempts", 0) + 1
    tool_context.state["sample_attempts"] = attempts

    story_writer_output = tool_context.state.get("story_writer_output")
    illustrator_concept_output = tool_context.state.get("illustrator_concept_output")
    art_style_guide = illustrator_concept_output.get("art_style_guide")
    character_sheet = illustrator_concept_output.get("character_sheet")
    pages = story_writer_output.get("pages")
    title = story_writer_output.get("title")

    safe_title = re.sub(r'[<>:"/\\|?*]', "", title)
    safe_title = safe_title.replace(" ", "_")

    generated_images = []
    existing_artifacts = await tool_context.list_artifacts()

    for page in pages:
        page_number = page.get("page_number")
        illustration_description = page.get("illustration_description")
        enhanced_prompt = art_style_guide + ', ' + character_sheet + ', ' + illustration_description
        filename = f"{safe_title}_{attempts}_page_{page_number}_image.jpeg"
        path = local_path(filename)

        if filename in existing_artifacts:
            generated_images.append(
                {
                    "page_number": page_number,
                    "image_prompt": illustration_description,
                    "filename": filename,
                }
            )
            continue

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

        save_local(filename, image_bytes)
        await save_artifact(tool_context, filename, image_bytes)

        generated_images.append(
            {
                "page_number": page_number,
                "image_prompt": illustration_description,
                "filename": filename,
            }
        )

    _mark_pages_generated(
        tool_context, {p["page_number"]: p["filename"] for p in generated_images}
    )

    return {
        "pages": generated_images,
    }

async def generate_page_image(
    page_number: int,
    additional_prompt: str,
    tool_context: ToolContext,
) -> dict:
    """Regenerate a single page image with an additional correction prompt appended to the illustration description."""
    attempts = tool_context.state.get("sample_attempts", 0) + 1
    tool_context.state["sample_attempts"] = attempts
    
    story_writer_output = tool_context.state.get("story_writer_output")
    illustrator_concept_output = tool_context.state.get("illustrator_concept_output")
    art_style_guide = illustrator_concept_output.get("art_style_guide")
    character_sheet = illustrator_concept_output.get("character_sheet")
    pages = story_writer_output.get("pages")
    title = story_writer_output.get("title")

    safe_title = re.sub(r'[<>:"/\\|?*]', "", title)
    safe_title = safe_title.replace(" ", "_")


    page = next((p for p in pages if p.get("page_number") == page_number), None)
    if page is None:
        tool_context.state["illustrator_generation_status"] = None
        return {"error": f"page_number {page_number} not found"}

    illustration_description = page.get("illustration_description", "")
    enhanced_prompt = art_style_guide + ', ' + character_sheet + ', ' + illustration_description
    image_prompt = illustration_description
    if additional_prompt:
        enhanced_prompt += '. ' + additional_prompt
        image_prompt = illustration_description + '. ' + additional_prompt

    filename = f"{safe_title}_{attempts}_page_{page_number}_image.jpeg"

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

    path = save_local(filename, image_bytes)
    await save_artifact(tool_context, filename, image_bytes)

    _mark_pages_generated(tool_context, {page_number: filename})

    return {
        "page_number": page_number,
        "image_prompt": image_prompt,
        "filename": filename,
    }
