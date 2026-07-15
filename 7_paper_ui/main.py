import dotenv
dotenv.load_dotenv()

import streamlit as st
from langchain_core.messages import HumanMessage

from graph import graph

st.set_page_config(layout="wide")
st.title("논문 탐사 춘냥이")

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = "session-1"

config = {"configurable": {"thread_id": st.session_state["thread_id"]}}

state = graph.get_state(config)
values = state.values if state.values else {}
messages = values.get("messages", [])
summaries = values.get("summaries", [])

with st.sidebar:
    st.header("논문 목록")
    if summaries:
        options = [f"{s['id']}. {s['title']}" for s in summaries]
        selected_label = st.selectbox("요약을 확인할 논문을 선택하세요", options)
        selected_summary = summaries[options.index(selected_label)]
    else:
        selected_summary = None
        st.write("아직 요약된 논문이 없습니다.")

left_col, right_col = st.columns([1, 2])

with left_col:
    st.subheader("논문 요약")
    if selected_summary:
        st.markdown(f"**{selected_summary['title']}**")
        st.write(f"평점: {selected_summary['rating']}")
        st.write(f"**읽어야 할 이유**: {selected_summary['why_read']}")
        st.write(f"**넘어가도 될 이유**: {selected_summary['why_skip']}")
        st.write("**핵심 요약**")
        st.write(selected_summary["summmary"])
        st.write("**Key Takeaways**")
        for item in selected_summary["key_takeaways"]:
            st.write(f"- {item}")
        st.write("**적용 아이디어**")
        for item in selected_summary["application_ideas"]:
            st.write(f"- {item}")
    else:
        st.write("왼쪽에는 선택된 논문 요약이 표시됩니다.")

with right_col:
    st.subheader("채팅")
    for msg in messages:
        role = "human" if isinstance(msg, HumanMessage) else "ai"
        with st.chat_message(role):
            st.write(msg.content)

    user_input = st.chat_input("메시지를 입력하세요")
    
    if user_input:
        with right_col:
            with st.chat_message("human"):
                st.write(user_input)

            graph.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
            )

        st.rerun()
    