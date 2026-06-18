import dotenv
dotenv.load_dotenv()

from openai import OpenAI
import asyncio
import base64
import streamlit as st
import re

from agents import (
    Agent,
    Runner,
    SQLiteSession,
    WebSearchTool,
    FileSearchTool,
    ImageGenerationTool,
)

client = OpenAI()

VECTOR_STORE_ID = "vs_6a335e645848819197e6b5ddc8282b3f"

if "session" not in st.session_state:
    st.session_state["session"] = SQLiteSession(
        "chat-history",
        "agent-memory.db",
    )
session = st.session_state["session"]

async def paint_history():
    messages = await session.get_items()
    # if len(messages)>0:
    #     print(type(messages[0]))

    for message in messages:
        
        if "role" in message:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    content = message["content"]
                    if isinstance(content, str):
                        st.write(content)
                    elif isinstance(content, list):
                        for part in content:
                            if "image_url" in part:
                                st.image(part["image_url"])

                else:
                    if message["type"] == "message":
                        content = message["content"][0]
                        text = content.get("text")
                        text = re.sub(r"", "", text)# filecite 제거

                        if "annotations" in content:
                            filenames = set()
                            for annotation in content.get("annotations", []):
                                if annotation["type"] == "file_citation":
                                    filenames.add(annotation.get("filename"))

                            if filenames:
                                text += "\n\n" + ", ".join(f"[{name}]" for name in filenames)
                                    
                        st.write(text.replace("$", "\$"))
                        
        if "type" in message:
            message_type = message["type"]
            if message_type == "web_search_call":
                if "action" in message:
                    query = message["action"].get("query")
                with st.chat_message("ai"):
                    st.write("🔍 웹 검색: ", query)
            elif message_type == "file_search_call":
                with st.chat_message("ai"):
                    st.write("🗂️ 파일 검색")
            elif message_type == "image_generation_call":
                image = base64.b64decode(message["result"])
                with st.chat_message("ai"):
                    st.image(image)

asyncio.run(paint_history())

def update_status(status_container, event):
    status_messages = {
        "response.web_search_call.completed": ("✅ Web search completed.", "complete"),
        "response.web_search_call.in_progress": (
            "🔍 Starting web search...",
            "running",
        ),
        "response.web_search_call.searching": (
            "🔍 Web search in progress...",
            "running",
        ),
        "response.file_search_call.completed": (
            "✅ File search completed.",
            "complete",
        ),
        "response.file_search_call.in_progress": (
            "🗂️ Starting file search...",
            "running",
        ),
        "response.file_search_call.searching": (
            "🗂️ File search in progress...",
            "running",
        ),
        "response.image_generation_call.generating": (
            "🎨 Drawing image...",
            "running",
        ),
        "response.image_generation_call.in_progress": (
            "🎨 Drawing image...",
            "running",
        ),
        "response.completed": (" ", "complete"),
    }

    if event in status_messages:
        label, state = status_messages[event]
        status_container.update(label=label, state=state)

from agents.run import RunConfig

def sanitize_session_history(history: list[dict], new_input: list[dict]) -> list[dict]:
    """
    세션 DB에서 불러온 기록(history) 중 
    ImageGenerationTool 등으로 인해 생성된 불필요한 'action' 키를 정제합니다.
    """
    cleaned_history = []
    for item in history:
        # dict 형태일 때 action 키가 있다면 제거하여 스키마 충돌 방지
        if isinstance(item, dict) and "action" in item:
            item = item.copy()  # 원본 훼손 방지 카피
            item.pop("action", None)
        cleaned_history.append(item)
        
    # 정제된 과거 기록과 새로운 유저 메시지를 합쳐서 리턴
    return cleaned_history + new_input

# run_config에 콜백 등록
config = RunConfig(session_input_callback=sanitize_session_history)

INST = """
당신은 따뜻하고 격려적인 Life Coach입니다.
동기부여, 자기계발, 습관 형성에 대한 맞춤형 조언을 제공합니다.

역할:
- 사용자의 목표 달성을 진심으로 축하하고 동기를 부여합니다.
- 항상 웹 검색을 통해 관련 정보를 확인합니다.
- 근거가 불분명한 내용은 추측하지 않습니다.
- 파일 검색으로 사용자의 저장된 목표/계획 문서를 참고합니다.
- 축하할 일이 생기거나 비전 보드·영감 이미지가 필요하면 반드시 ImageGenerationTool을 호출합니다.

응답 스타일:
- 친근하고 격려하는 말투를 사용합니다.
- 쉽고 간결하게 설명합니다.
- 이미지를 생성할 때는 "이미지를 만들어 드릴게요 🎨" 같이 먼저 안내합니다.

사용자가 목표 달성, 성과, 습관 성공을 이야기하면:

1. 축하한다.
2. 필요시 목표 문서를 검색한다.
3. 기념 이미지를 생성한다.
4. 생성된 이미지를 사용자에게 보여준다.

비전보드를 요청하면:

1. 목표 문서를 먼저 검색한다.
2. 주요 목표를 추출한다.
3. 비전보드 이미지 프롬프트를 작성한다.
4. 이미지 생성 툴을 호출한다.

조언을 요청하면
1. 필요시 목표문서를 검색한다.
2. Web Search Tool을 호출하여 동기부여 콘텐츠, 습관형성 전략 등을 검색한다.

"""

async def run_agent(message):
    agent = Agent(
        name="Life Coach",
        instructions=INST,
        tools=[
            WebSearchTool(),
            FileSearchTool(
                    vector_store_ids=[VECTOR_STORE_ID],
                    max_num_results=3,
                ),
            ImageGenerationTool(
                    tool_config={
                        "type": "image_generation",
                        "quality": "low",
                        "output_format": "jpeg",
                        "partial_images": 1,
                        "size": "1024x1024",
                    }
                ),
        ],
    )

    with st.chat_message("ai"):
        status_container = st.status("⏳", expanded=False)
        image_placeholder = st.empty()
        text_placeholder = st.empty()
        response = ""
        
        st.session_state["text_placeholder"] = text_placeholder
        st.session_state["image_placeholder"] = image_placeholder
        
        stream = Runner.run_streamed(
            agent,
            message,
            session=session,
            run_config=config,
        )
    
        async for event in stream.stream_events():
            if event.type == "raw_response_event":
            
                update_status(status_container, event.data.type)
                
                if event.data.type == "response.output_text.delta":
                    response += event.data.delta
                    text_placeholder.write(response.replace("$", "\$"))
                    
                if (
                        event.data.type
                        == "response.image_generation_call.partial_image"
                    ):
                        image = base64.b64decode(event.data.partial_image_b64)
                        image_placeholder.image(image)

prompt = st.chat_input(
    "Write a message for your assistant",
    accept_file=True,
    file_type=[
        "txt",
        "pdf",
    ],
)

if prompt:
    if "image_placeholder" in st.session_state:
        st.session_state["image_placeholder"].empty()
    if "text_placeholder" in st.session_state:
        st.session_state["text_placeholder"].empty()

    for file in prompt.files:
        if (file.type.startswith("text/") or file.type == "application/pdf"):
            with st.chat_message("ai"):
                with st.status("⏳ Uploading file...") as status:
                    uploaded_file = client.files.create(
                        file=(file.name, file.getvalue()),
                        purpose="user_data",
                    )
                    status.update(label="⏳ Attaching file...")
                    client.vector_stores.files.create(
                        vector_store_id=VECTOR_STORE_ID,
                        file_id=uploaded_file.id,
                    )
                    status.update(label="✅ File uploaded", state="complete")
                    
    if prompt.text:
        with st.chat_message("human"):
            st.write(prompt.text)
        asyncio.run(run_agent(prompt.text))


with st.sidebar:
    reset = st.button("Reset memory")
    if reset:
        asyncio.run(session.clear_session())
    st.write(asyncio.run(session.get_items()))
