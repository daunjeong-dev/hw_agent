import base64
import io
import re
from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
from PIL import Image
from storybook_agent.image_utils import local_path, save_local

DISPLAY_IMAGE_SIZE = (256, 256)


async def render_storybook_markdown(tool_context: ToolContext) -> dict:
    """Assembles the finished storybook into Markdown and saves it to disk.

    Reads directly from illustrator_output/story_writer_output rather than
    letting the model retype page text or filenames, so the result always
    matches what was actually generated.

    The .md file itself can't embed a working image URL for chat display —
    ADK's artifact endpoint returns a JSON-wrapped Part, not a browser-servable
    image URL — so it's saved next to the generated jpegs (same output/
    folder) with bare relative filenames, for opening in a local Markdown
    viewer. Inline chat display is instead handled by
    build_illustrated_content, which reads the same state this function reads
    and is wired up as display_agent's after_agent_callback.
    """
    story_writer_output = tool_context.state.get("story_writer_output", {})
    illustrator_output = tool_context.state.get("illustrator_output", {})

    title = illustrator_output.get("title") or story_writer_output.get("title", "")
    pages = sorted(
        illustrator_output.get("pages", []),
        key=lambda page: int(page.get("page_number", 0)),
    )

    lines = [f"# {title}", ""]
    for page in pages:
        page_number = page.get("page_number")
        filename = page.get("filename", "")
        lines.append(f"## {page_number}페이지")
        lines.append("")
        lines.append(f"![{page_number}페이지 삽화]({filename})")
        lines.append("")
        lines.append(page.get("text", ""))
        lines.append("")

    markdown = "\n".join(lines).strip()

    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_") or "storybook"
    # await tool_context.save_artifact(filename=f"{safe_title}.md", artifact=types.Part.from_text(text=markdown))
    save_local(f"{safe_title}.md", markdown.encode("utf-8"))

    return {
        "markdown": markdown,
    }


def build_illustrated_content(callback_context: CallbackContext) -> types.Content | None:
    """Builds one Content with each page's text and its illustration embedded
    as a markdown ![]() data: URI, so adk web's chat renders the storybook
    directly instead of only the saved .md file having it.

    Deliberately NOT a types.Part(inline_data=Blob(...)): google-genai
    serializes Blob.data as URL-safe base64 (pydantic's bytes JSON mode), but
    adk web's frontend builds the <img> "data:...;base64," src by
    concatenating that string as-is, which only decodes as *standard*
    base64 — so any inline_data image with '-'/'_' in its encoding (i.e.
    almost every real image) silently fails to render. Embedding a
    standard-base64 data URI inside a plain text Part sidesteps that bytes
    serialization path entirely, and adk web renders assistant text through
    ngx-markdown, so the ![]() turns into a working <img>.

    Reads illustrator_output/story_writer_output from state (same source as
    render_storybook_markdown above) and reads the image bytes back from
    output/<filename>, since state only ever holds the filename, not the
    bytes themselves.
    """
    story_writer_output = callback_context.state.get("story_writer_output", {})
    illustrator_output = callback_context.state.get("illustrator_output", {})

    title = illustrator_output.get("title") or story_writer_output.get("title", "")
    pages = sorted(
        illustrator_output.get("pages", []),
        key=lambda page: int(page.get("page_number", 0)),
    )
    if not pages:
        return None

    parts = [types.Part(text=f"# {title}\n\n")]
    for page in pages:
        page_number = page.get("page_number")
        filename = page.get("filename", "")
        parts.append(types.Part(text=f"## {page_number}페이지\n"))

        try:
            with open(local_path(filename), "rb") as f:
                image_bytes = f.read()
        except OSError:
            continue

        with Image.open(io.BytesIO(image_bytes)) as image:
            resized = image.convert("RGB").resize(DISPLAY_IMAGE_SIZE)
            buffer = io.BytesIO()
            resized.save(buffer, format="JPEG")
            image_bytes = buffer.getvalue()

        encoded = base64.b64encode(image_bytes).decode("ascii")
        parts.append(
            types.Part(
                text=f"![{page_number}페이지 삽화](data:image/jpeg;base64,{encoded})\n"
            )
        )
        parts.append(types.Part(text="\n" + page.get("text", "") + "\n\n"))

    return types.Content(role="model", parts=parts)
