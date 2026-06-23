"""
Life Coach Agent - OpenAI Agents SDK
Tools: WebSearchTool, FileSearchTool, Image Generation (DALL-E via function tool)
"""

import asyncio
import base64
import os
from pathlib import Path
from openai import AsyncOpenAI
from agents import Agent, Runner, WebSearchTool, FileSearchTool, function_tool

# ── 설정 ──────────────────────────────────────────────────────────────────────
VECTOR_STORE_ID = os.environ.get("VECTOR_STORE_ID", "vs_xxxx")   # 본인 ID로 교체
IMAGE_OUTPUT_DIR = Path("generated_images")
IMAGE_OUTPUT_DIR.mkdir(exist_ok=True)

openai_client = AsyncOpenAI()

# ── 시스템 프롬프트 ────────────────────────────────────────────────────────────
INST = """
당신은 따뜻하고 격려적인 라이프 코치입니다.

역할:
- 사용자의 목표 달성을 진심으로 축하하고 동기를 부여합니다.
- 필요하면 웹 검색으로 최신 정보를 찾아 조언합니다.
- 파일 검색으로 사용자의 저장된 목표/계획 문서를 참고합니다.
- 축하할 일이 생기거나 비전 보드·영감 이미지가 필요하면 반드시 generate_image 툴을 호출합니다.

이미지 생성 기준:
1. 목표 달성 보고 → 축하 이미지 생성
2. 비전 보드 요청 → 목표 키워드를 담은 비전 보드 이미지 생성
3. 영감/동기 부여 요청 → 관련 이미지 생성

응답 스타일:
- 한국어로 따뜻하고 친근하게 대화합니다.
- 이모지를 적절히 사용합니다.
- 이미지를 생성할 때는 "이미지를 만들어 드릴게요 🎨" 같이 먼저 안내합니다.
"""

# ── 이미지 생성 툴 ─────────────────────────────────────────────────────────────
@function_tool
async def generate_image(prompt: str, filename: str = "image") -> str:
    """
    DALL-E 3를 사용해 이미지를 생성하고 로컬에 저장합니다.

    Args:
        prompt: 생성할 이미지에 대한 영어 설명 (구체적이고 시각적으로 기술)
        filename: 저장할 파일 이름 (확장자 제외)

    Returns:
        저장된 이미지 경로와 생성 완료 메시지
    """
    print(f"\n🎨 이미지 생성 중... prompt: {prompt[:80]}...")

    response = await openai_client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        response_format="b64_json",
        n=1,
    )

    image_data = response.data[0].b64_json
    revised_prompt = response.data[0].revised_prompt or prompt

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in filename)
    output_path = IMAGE_OUTPUT_DIR / f"{safe_name}.png"
    output_path.write_bytes(base64.b64decode(image_data))

    print(f"✅ 이미지 저장 완료: {output_path}")
    return (
        f"이미지가 성공적으로 생성되어 '{output_path}' 에 저장되었습니다.\n"
        f"실제 사용된 프롬프트: {revised_prompt}"
    )


# ── 에이전트 팩토리 ────────────────────────────────────────────────────────────
def build_agent() -> Agent:
    return Agent(
        name="Life Coach",
        instructions=INST,
        tools=[
            WebSearchTool(),
            FileSearchTool(
                vector_store_ids=[VECTOR_STORE_ID],
                max_num_results=3,
            ),
            generate_image,
        ],
    )


# ── 단일 턴 실행 ───────────────────────────────────────────────────────────────
async def run_agent(message: str) -> str:
    agent = build_agent()
    result = await Runner.run(agent, message)
    return result.final_output


# ── 멀티 턴 대화 루프 ──────────────────────────────────────────────────────────
async def chat_loop() -> None:
    """터미널에서 Life Coach와 대화하는 인터랙티브 루프."""
    agent = build_agent()
    history: list[dict] = []

    print("=" * 60)
    print("  🌟 Life Coach 에이전트에 오신 것을 환영합니다!")
    print("  종료하려면 'quit' 또는 'exit' 를 입력하세요.")
    print("=" * 60)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n대화를 종료합니다. 좋은 하루 되세요! 👋")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "종료"}:
            print("대화를 종료합니다. 좋은 하루 되세요! 👋")
            break

        history.append({"role": "user", "content": user_input})

        print("\nCoach: ", end="", flush=True)
        result = await Runner.run(agent, history)
        reply = result.final_output

        print(reply)
        history.append({"role": "assistant", "content": reply})


# ── 엔트리포인트 ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 단일 테스트
    # asyncio.run(run_agent("올해 책 10권 읽기 목표를 달성했어!"))

    # 인터랙티브 대화
    asyncio.run(chat_loop())
