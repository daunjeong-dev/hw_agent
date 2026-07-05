import base64
import re
from openai import OpenAI
from google.adk.tools.tool_context import ToolContext
from storybook_agent.image_utils import save_local, save_artifact

client = OpenAI()

async def generate_sample_image(
    art_style_guide: str,
    character_sheet: str,
    tool_context: ToolContext,
) -> dict:
    """Generate a sample image and ask the user to confirm before proceeding."""
    attempts = tool_context.state.get("sample_attempts", 0) + 1
    tool_context.state["sample_attempts"] = attempts

    story_output = tool_context.state.get("story_writer_output")
    if story_output is None:
        return {
            "message": f"스토리가 작성되지 않았습니다. 완료후에 시도해주세요."
        }
    
    title = story_output.get("title")

    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_")[:7]

    filename = f"{attempts}_{safe_title}_sample_attempt.jpeg"
    final_prompt = "art_style_guide: " + art_style_guide + "\ncharacter_sheet: " + character_sheet

    image = client.images.generate(
        model="gpt-image-1",
        prompt=final_prompt,
        n=1,
        quality="low",
        moderation="low",
        output_format="jpeg",
        background="opaque",
        size="1024x1024",
    )

    image_bytes = base64.b64decode(image.data[0].b64_json)

    await save_artifact(tool_context, filename, image_bytes)
    local_path = save_local(filename, image_bytes)

    tool_context.state["sample_generation_status"] = "PENDING_REVIEW"
    tool_context.state["sample_generation_filename"] = filename

    return {
        "filename": filename,
        "attempt": attempts,
        "message": f"샘플 이미지를 생성했습니다 ({filename}). 이 결과로 최종 출력을 작성하세요.",
        "status": "done",
    }
