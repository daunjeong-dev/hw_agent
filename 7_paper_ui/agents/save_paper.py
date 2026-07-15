from pydantic import BaseModel, Field
from typing import Literal
from langgraph.types import Command

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from langgraph.graph import END

from agents.supervisor import State
from prompts.save_paper import QNA_SYSTEM_PROMPT
from tools.save_paper import save_qna_as_markdown, load_graph_from_disk, update_graph, save_graph_to_disk

import networkx as nx

MAX_N_KEYWORDS = 8
class ConversationSummary(BaseModel):
    qna_summary: str = Field(
        description="대화의 핵심 내용을 3~5문장으로 요약"
    )

    keywords: list[str] = Field(
        description="핵심 키워드 8개, 짧은 명사구"
    )

keyword_llm = init_chat_model("openai:gpt-4o-mini").with_structured_output(ConversationSummary)
def extract_keywords(qna_history: list[BaseMessage]) -> list[str]:
    qna_text = "\n".join(f"{m.type}: {m.content}" for m in qna_history[1:])
    result = keyword_llm.invoke([
        SystemMessage(content=QNA_SYSTEM_PROMPT),
        HumanMessage(content=qna_text),
    ])
    return result.model_dump()

def save_paper(state: State):
    keywords = extract_keywords(state["assumption_qna"])
    selected_paper_num = int(state.get("selected_paper_num", 1)) -1

    md_path = save_qna_as_markdown(
        state["papers"][selected_paper_num], state["summaries"][selected_paper_num], keywords
    )

    # State에 없으면 디스크에 누적된 그래프를 로드 (State에는 직렬화된 dict로 저장)
    paper_graph = nx.node_link_graph(state["paper_graph"]) if state.get("paper_graph") else load_graph_from_disk()
    keywords_ai = keywords.get("keywords",[])
    if len(keywords_ai)<1:
        keywords_ai = state["papers"][selected_paper_num].get("ai_keywords",[])
    
    if len(keywords_ai)>0:
        keywords_ai = keywords_ai[:MAX_N_KEYWORDS]
        paper_graph = update_graph(paper_graph, state["papers"][selected_paper_num], keywords_ai)
        save_graph_to_disk(paper_graph)  # 종료/논문 전환 전에 디스크에 영속화
        return {
            "paper_graph": nx.node_link_data(paper_graph),
            "messages": [AIMessage(content="논문 내용 저장되었습니다.")]}  # dict로 저장
    return
