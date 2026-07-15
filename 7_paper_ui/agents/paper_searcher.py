
import streamlit as st
from dateutil.relativedelta import relativedelta
from datetime import date
from pydantic import BaseModel, Field
from typing import Literal
from langgraph.types import Send, Command

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agents.supervisor import State, RESET_SUMMARIES
from prompts.paper_searcher import SEARCH_PROMPT
from tools.paper_searcher import fetch_from_huggingface, score_and_sort, fetch_title_from_huggingface

# ---- 파라미터 추출 스키마 (structured output) ----
class SearchQueryParams(BaseModel):
    search_type: Literal["title", "query"] = Field(description="논문 검색 방법 제목 or 키워드/기간")

    title: str | None = Field(description="검색할 논문 제목")

    topic: str | None = Field(description="검색할 논문 주제/키워드")
    year_delta: int = Field(default=0, description="검색 기간 년")
    month_delta: int = Field(default=0, description="검색 기간 월")
    day_delta: int = Field(default=14, description="검색 기간 일")
    count: int = Field(default=2, description="수집할 논문 개수")

SYSTEM_MESSAGE = SystemMessage(content=SEARCH_PROMPT)
llm = init_chat_model("openai:gpt-4o-mini")
def llm_extract_params(raw_query: str) -> dict:
    structured_llm = llm.with_structured_output(SearchQueryParams)
    result = structured_llm.invoke([
        SYSTEM_MESSAGE,
        HumanMessage(content=raw_query)])
    return result.model_dump()

def parse_search_query(state: State):
    parsed = llm_extract_params(state["user_request"])

    search_type = parsed.get("search_type", "query")
    
    if search_type == "query":

        today = date.today()
    
        start_date = today - relativedelta(
        years=parsed.get("year_delta",0),
        months=parsed.get("month_delta",0),
        days=parsed.get("day_delta",0),
        )
        return Command(
        goto="keyword_paper_searcher",
        update={
            "topic": parsed.get("topic",""),
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "count": parsed.get("count",2),
        })
    else:
        return Command(
        goto="title_paper_searcher",
        update={
            "title": parsed.get("title", ""),
            "count": 2,
        })
    
def keyword_paper_searcher(state: State):
    progress_placeholder = st.empty()
    raw_papers = fetch_from_huggingface(
        state["topic"], state["start_date"], state["end_date"], state["count"],
        on_progress=progress_placeholder.write,
    )
    progress_placeholder.empty()
    raw_papers = score_and_sort(raw_papers)
    if len(raw_papers) > state["count"]:
        scored = raw_papers[: state["count"]]
    else:
        scored = raw_papers
    return {"papers": scored,
            "messages": [AIMessage(content="기간별 논문 서치 완료되었습니다.")],
            "summaries": [RESET_SUMMARIES]}

def title_paper_searcher(state: State):
    # raw_papers = fetch_title_from_huggingface(
    #     state["topic"], state["start_date"], state["end_date"], state["count"]
    # )
    # if len(raw_papers) > state["count"]:
    #     raw_papers = raw_papers[: state["count"]]

    return {"messages": [AIMessage(content="현재 지정 논문 서치를 사용할 수 없습니다.")],
            }

def dispatch_summarizers(state: State):
    papers = state["papers"]
    meta_infos = []
    for i, paper in enumerate(papers):
        meta_infos.append({"id": i + 1, "paper": paper})
        print(i)
    return [Send("summarize_paper", meta_info) for meta_info in meta_infos]