import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage

from agents.supervisor import State, supervisor
from agents.paper_searcher import parse_search_query, dispatch_summarizers, keyword_paper_searcher, title_paper_searcher
from agents.summarize_paper import summarize_paper, present_summaries
from agents.user_select_paper import user_select_paper
from agents.assumption_qna import assumption_qna
from agents.save_paper import save_paper
from agents.respond_directly import respond_directly

builder = StateGraph(State)
builder.add_node("supervisor", supervisor)

builder.add_node("parse_search_query", parse_search_query)
builder.add_node("keyword_paper_searcher", keyword_paper_searcher)
builder.add_node("title_paper_searcher", title_paper_searcher)
builder.add_node("summarize_paper", summarize_paper)
builder.add_node("present_summaries", present_summaries)
builder.add_node("user_select_paper", user_select_paper)
builder.add_node("assumption_qna", assumption_qna)
builder.add_node("save_paper", save_paper)
builder.add_node("respond_directly", respond_directly)

builder.add_edge(START, "supervisor")
builder.add_conditional_edges(
    "keyword_paper_searcher", dispatch_summarizers, ["summarize_paper"]
)
builder.add_conditional_edges(
    "title_paper_searcher", dispatch_summarizers, ["summarize_paper"]
)
builder.add_edge("summarize_paper", "present_summaries")
builder.add_edge("present_summaries", END)
builder.add_edge("save_paper", END)
builder.add_edge("respond_directly", END)
# graph = builder.compile()

conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(conn)

graph = builder.compile(checkpointer=checkpointer)


# if __name__ == "__main__":
#     config = {"configurable": {"thread_id": "session-3"}}
 
#     print("논문 분석 챗봇 (종료: exit)")
#     while True:
#         user_input = input("> ")
#         if user_input.strip() == "exit":
#             break
 
#         result = graph.invoke(
#             {"messages": [HumanMessage(content=user_input)]},
#             config=config,
#         )
#         last_ai_message = result["messages"][-1]
#         print(f"[봇] {last_ai_message.content}")
 
# ---- 실행 예시 ----
# config = {"configurable": {"thread_id": "session-1"}}
# graph.invoke({"raw_query": "최근 2주간 Agent 논문 2개"}, config)

# # # ...interrupt 발생 후...
# response = {
#     "choice": 1,
# }
# graph.invoke(Command(resume=response), config)
# # # ...interrupt 2...
# response = "잘모르겠다"
# graph.invoke(Command(resume=response), config)

# response = "잘모르겠다"
# graph.invoke(Command(resume=response), config)

# # response = "다음 논문"
# # graph.invoke(Command(resume=response), config)

# response = "종료"
# graph.invoke(Command(resume=response), config)

# graph.invoke({"raw_query": "그래프 그림 그려줘"}, config)