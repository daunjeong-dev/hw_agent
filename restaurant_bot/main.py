import dotenv
dotenv.load_dotenv()

from openai import OpenAI
import asyncio
import streamlit as st
import json
from agents import Runner, SQLiteSession, InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered
from models import UserAccountContext
from my_agents.triage_agent import triage_agent

client = OpenAI()

user_account_ctx = UserAccountContext(
    customer_id=1,
    name="Un",
    phone="01012345678"
)

if "session" not in st.session_state:
    st.session_state["session"] = SQLiteSession(
        "chat-history",
        "customer-support-memory.db",
    )
session = st.session_state["session"]

if "order_store" not in st.session_state:
    st.session_state["order_store"] = {}

if "agent" not in st.session_state:
    st.session_state["agent"] = triage_agent

async def paint_history():
    messages = await session.get_items()
    for message in messages:
        if "role" in message:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.write(message["content"])
                else:
                    if message["type"] == "message":
                        st.write(message["content"][0]["text"].replace("$", "\$"))

        if "type" in message:
            message_type = message["type"]
            if message_type == "function_call":
                name = message.get("name","")
                with st.chat_message("ai"):
                    st.write(f"{name}: {message.get("arguments","")}")

                    
asyncio.run(paint_history())


async def run_agent(message):

    with st.chat_message("ai"):
        text_placeholder = st.empty()
        response = ""

        st.session_state["text_placeholder"] = text_placeholder

        try:

            stream = Runner.run_streamed(
                st.session_state["agent"],
                message,
                session=session,
                context=user_account_ctx,
            )

            async for event in stream.stream_events():
                if event.type == "raw_response_event":

                    if event.data.type == "response.output_text.delta":
                        response += event.data.delta
                        text_placeholder.write(response.replace("$", "\$"))

                elif event.type == "agent_updated_stream_event":

                    if st.session_state["agent"].name != event.new_agent.name:
                        
                        st.write(f'🤖 Transfered from {st.session_state["agent"].name} to {event.new_agent.name}')

                        st.session_state["agent"] = event.new_agent

                        text_placeholder = st.empty()

                        st.session_state["text_placeholder"] = text_placeholder
                        response = ""

        except InputGuardrailTripwireTriggered:
            st.write("Input Guard Rail 작동")
            response = "안녕하세요 :) 레스토랑 관련 문의만 도와드릴 수 있습니다. 메뉴, 주문, 예약, 불만 사항을 말씀해주세요."
            text_placeholder.write(response)
            await session.pop_item()

        except OutputGuardrailTripwireTriggered:
            st.write("Output Guard Rail 작동")
            response = "Cant show you that answer."
            text_placeholder.write(response)
            await session.pop_item()

message = st.chat_input(
    "Write a message for your assistant",
)

if message:
    with st.chat_message("human"):
        st.write(message)
    asyncio.run(run_agent(message))
    
with st.sidebar:
    reset = st.button("Reset memory")
    if reset:
        asyncio.run(session.clear_session())
    st.write(asyncio.run(session.get_items()))