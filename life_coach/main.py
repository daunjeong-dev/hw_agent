import dotenv
dotenv.load_dotenv()

from openai import OpenAI
import asyncio
import streamlit as st

from agents import (
    Agent,
    Runner,
    SQLiteSession,
    WebSearchTool,
)

client = OpenAI()

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
                        st.write(message["content"][0]["text"].replace("$", "\$"))
                        
        if "type" in message:
            message_type = message["type"]
            if message_type == "web_search_call":
                if "action" in message:
                    query = message["action"].get("query")
                with st.chat_message("ai"):
                    st.write("🔍 웹 검색: ", query)

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
        # "response.completed": (" ", "complete"),
    }

    if event in status_messages:
        label, state = status_messages[event]
        status_container.update(label=label, state=state)

INST = """
당신은 Life Coach입니다.

목표:
사용자가 성장하고 좋은 습관을 만들 수 있도록 돕습니다.

행동 지침:
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
"""

async def run_agent(message):
    agent = Agent(
        name="Life Coach",
        instructions=INST,
        tools=[
            WebSearchTool(),
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
)

if prompt:
    if "text_placeholder" in st.session_state:
        st.session_state["text_placeholder"].empty()

    with st.chat_message("human"):
        st.write(prompt)
    asyncio.run(run_agent(prompt))


with st.sidebar:
    reset = st.button("Reset memory")
    if reset:
        asyncio.run(session.clear_session())
    st.write(asyncio.run(session.get_items()))

