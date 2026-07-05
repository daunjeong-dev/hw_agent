import dotenv
dotenv.load_dotenv()

from openai import OpenAI
import asyncio
import streamlit as st
import re

from agents import (
    Agent,
    Runner,
    SQLiteSession,
    WebSearchTool,
    FileSearchTool,
)

client = OpenAI()

VECTOR_STORE_ID = "vs_6a2f9297926c8191aa0440c313fb0e75"

if "session" not in st.session_state:
    st.session_state["session"] = SQLiteSession(
        "chat-history",
        "life-coach-memory.db",
    )
session = st.session_state["session"]

async def paint_history():
    messages = await session.get_items()
    
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
        "response.completed": (" ", "complete"),
    }

    if event in status_messages:
        label, state = status_messages[event]
        status_container.update(label=label, state=state)

INST = """
당신은 Life Coach입니다.

목표:
사용자와 대화하며 동기부여, 자기계발, 습관 형성에 대한 맞춤형 조언을 제공합니다.

규칙:
- 항상 검색을 통해 관련 정보를 확인합니다.
- 검색 결과를 요약하여 핵심만 전달합니다.
- 추천 시 이유와 기대 효과를 설명합니다.
- 사용자의 목표, 현재 상황, 피드백을 반영합니다.
- 정보가 부족하면 질문을 통해 먼저 파악합니다.
- 근거가 불분명한 내용은 추측하지 않습니다.

대화 스타일:
- 친근하고 격려하는 말투를 사용합니다.
- 쉽고 간결하게 설명합니다.
- 사용자가 바로 실천할 수 있는 행동을 제안합니다.

도구 사용:
- Web Search Tool:
  동기부여 콘텐츠, 자기계발 방법, 습관 형성 전략 등 최신 정보를 찾을 때 사용합니다.
  추천 내용의 근거를 확인할 때 사용합니다.
- File Search Tool:
  사용자의 개인 목표 문서나 업로드된 파일 내용을 확인할 때 사용합니다.
  사용자의 목표, 습관, 계획과 관련된 질문에 답할 때 우선 활용합니다.
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
        ],
    )

    with st.chat_message("ai"):
        status_container = st.status("⏳", expanded=False)
        text_placeholder = st.empty()
        response = ""
        st.session_state["text_placeholder"] = text_placeholder
        
        stream = Runner.run_streamed(
            agent,
            message,
            session=session,
        )
    
        async for event in stream.stream_events():
            if event.type == "raw_response_event":
            
                update_status(status_container, event.data.type)
                
                if event.data.type == "response.output_text.delta":
                    response += event.data.delta
                    text_placeholder.write(response.replace("$", "\$"))

prompt = st.chat_input(
    "Write a message for your assistant",
    accept_file=True,
    file_type=[
        "txt",
        "pdf",
        "jpg",
        "jpeg",
        "png",
    ],
)

if prompt:
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

