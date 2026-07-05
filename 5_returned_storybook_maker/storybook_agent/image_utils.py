import os
from google.genai import types
from google.adk.tools.tool_context import ToolContext

OUTPUT_DIR = "output"


def local_path(filename: str) -> str:
    return f"{OUTPUT_DIR}/{filename}"


def save_local(filename: str, image_bytes: bytes) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = local_path(filename)
    with open(path, "wb") as f:
        f.write(image_bytes)
    return path


async def save_artifact(tool_context: ToolContext, filename: str, image_bytes: bytes):
    artifact = types.Part(
        inline_data=types.Blob(
            mime_type="image/jpeg",
            data=image_bytes,
        )
    )
    await tool_context.save_artifact(filename=filename, artifact=artifact)
