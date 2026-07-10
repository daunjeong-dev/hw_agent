import sqlite3
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import TypedDict, List, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, interrupt, Command

from openai import OpenAI
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, RemoveMessage, BaseMessage
from langgraph.graph.message import add_messages, REMOVE_ALL_MESSAGES
from pydantic import BaseModel, Field
from typing_extensions import Annotated
import math
import requests
import json
import networkx as nx

from langgraph.checkpoint.sqlite import SqliteSaver

from prompt import prompt, SUMMARY_SYSTEM_PROMPT, QUE_SYS_PROMPT, QNA_SYSTEM_PROMPT
from save_util import save_qna_as_markdown, update_graph, visualize_graph, load_graph_from_disk, save_graph_to_disk
from langgraph.prebuilt import ToolNode, tools_condition, InjectedState
from langchain_core.tools import tool

llm = init_chat_model("openai:gpt-4o-mini")

# ---- summaries 리셋용 sentinel 리듀서 ----
# operator.add만으로는 "빈 리스트를 더해서 리셋"이 안 되므로 (기존값 + [] == 기존값),
# RemoveMessage(REMOVE_ALL_MESSAGES) 패턴과 동일하게 sentinel로 명시적 리셋을 표현한다.
RESET_SUMMARIES = "__RESET_SUMMARIES__"  # object()는 checkpointer가 pending write를 msgpack 직렬화할 때 실패하므로 문자열 사용

def reset_or_add_summaries(left: list[dict], right: list[dict]) -> list[dict]:
    if right and right[0] == RESET_SUMMARIES:
        return right[1:]
    return left + right

# ---- State ----
class State(TypedDict):
    raw_query: str
    topic: str
    start_date: str
    end_date: str
    count: int
    papers: list[dict]
    summaries: Annotated[list[dict], reset_or_add_summaries]
    selected_id: int
    assumption_qna: Annotated[list[BaseMessage], add_messages]
    next_action: Literal["continue", "switch_paper", "end"]
    paper_graph: dict
    messages: Annotated[list[BaseMessage], add_messages]

MAX_ASSUMPTION_ROUNDS = 20  # 무한 루프 방지 하드 리밋

# ---- 파라미터 추출 스키마 (structured output) ----
class ExtractedQueryParams(BaseModel):
    topic: str = Field(description="검색할 논문 주제/키워드")
    year_delta: int = Field(description="검색 기간 년")
    month_delta: int = Field(description="검색 기간 월")
    day_delta: int = Field(description="검색 기간 일")
    count: int = Field(description="수집할 논문 개수")

def llm_extract_params(raw_query: str) -> dict:
    structured_llm = llm.with_structured_output(ExtractedQueryParams)
    result = structured_llm.invoke( prompt + raw_query)
    return result.model_dump()

# ---- 1. 파라미터 파싱 ----
def parse_query(state: State):
    parsed = llm_extract_params(state["raw_query"])
    today = date.today()

    start_date = today - relativedelta(
    years=parsed["year_delta"],
    months=parsed["month_delta"],
    days=parsed["day_delta"],
    )
    return {
        "topic": parsed["topic"],
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat(),
        "count": parsed["count"],
    }

# ---- 수집/스코어링 관련 상수 ----
HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
DAILY_PAPERS_PAGE_LIMIT = 50  # daily_papers 응답 페이지당 최대 개수
MIN_UPVOTES = 110  # 이 값 미만인 논문은 후보에서 제외
SCORE_WEIGHT_VOTES = 0.45
SCORE_WEIGHT_GITHUB_STARS = 0.35
SCORE_WEIGHT_RECENCY = 0.2
MIN_CANDIDATES_NUM = 50

# ---- 2. 수집 (결정적 로직, LLM 없음) ----
def fetch_from_huggingface(topic: str, start_date: str, end_date: str, count: int) -> list[dict]:
    topic_lower = topic.lower()
    first = date.fromisoformat(start_date)
    current = date.fromisoformat(end_date)

    candidates = []
    max_num = max(MIN_CANDIDATES_NUM, count*10)
    while current > first:
        response = requests.get(
            HF_DAILY_PAPERS_URL,
            params={"date": current.isoformat(), "limit": DAILY_PAPERS_PAGE_LIMIT},
            timeout=10,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError:
            if response.status_code == 400:
                # HF가 아직 발행하지 않은/허용하지 않는 날짜 (예: 오늘) -> 이 날짜만 건너뜀
                current -= timedelta(days=1)
                continue
            raise
        for item in response.json():
            paper = item["paper"]
            upvotes = paper.get("upvotes") or 0
            if upvotes < MIN_UPVOTES:
                break
            haystack = (paper["title"] + paper["summary"]).lower()
            if topic_lower not in haystack:
                continue
            candidates.append({
                "id": paper.get("id",""),
                "title": paper.get("title","-"),
                "summary": paper.get("summary","-"),
                "upvotes": upvotes,
                "github_stars": paper.get("githubStars") or 0,
                "github_repo": paper.get("githubRepo"),
                "published_at": paper.get("publishedAt",current),
                "project_page": paper.get("projectPage","-"),
                "ai_keywords": paper.get("ai_keywords",[]),
            })
        current -= timedelta(days=1)
        if len(candidates) > max_num:
            break

    return candidates


# ---- 2-1. 스코어링 (결정적 로직, LLM 없음) ----
def score_and_sort(papers: list[dict]) -> list[dict]:
    if not papers:
        return []

    def normalize(values: list[float]) -> list[float]:
        low, high = min(values), max(values)
        if high == low:
            return [1.0 for _ in values]
        return [(v - low) / (high - low) for v in values]

    vote_scores = normalize([math.log1p(p["upvotes"]) for p in papers])
    star_scores = normalize([math.log1p(p["github_stars"]) for p in papers])
    published_ts = [
        datetime.fromisoformat(p["published_at"]).timestamp() for p in papers
    ]
    recency_scores = normalize(published_ts)

    scored = []
    for paper, vote_score, star_score, recency_score in zip(
        papers, vote_scores, star_scores, recency_scores
    ):
        score = (
            SCORE_WEIGHT_VOTES * vote_score
            + SCORE_WEIGHT_GITHUB_STARS * star_score
            + SCORE_WEIGHT_RECENCY * recency_score
        )
        scored.append({**paper, "score": score})

    scored.sort(key=lambda p: p["score"], reverse=True)
    return scored

# ---- 2-2. 수집 + 스코어링 노드 ----
def fetch_and_score(state: State):
    raw_papers = fetch_from_huggingface(
        state["topic"], state["start_date"], state["end_date"], state["count"]
    )
    raw_papers = score_and_sort(raw_papers)
    if len(raw_papers) > state["count"]:
        scored = raw_papers[: state["count"]]
    else:
        scored = raw_papers
    return {"papers": scored,
            "summaries": [RESET_SUMMARIES]}

def dispatch_summarizers(state: State):
    papers = state["papers"]
    meta_infos = []
    for i, paper in enumerate(papers):
        meta_infos.append({"id": i + 1, "paper": paper})
    return [Send("summarize_paper", meta_info) for meta_info in meta_infos]

class PaperReview(BaseModel):
    rating: float = Field(description="1~5점")

    why_read: str
    why_skip: str

    key_takeaways: list[str]

    application_ideas: list[str]

    summmary: str

SYSTEM_MESSAGE = SystemMessage(content=SUMMARY_SYSTEM_PROMPT)
summary_structured_llm = llm.with_structured_output(PaperReview)
def summarize_paper(meta_info):
    paper_id = meta_info["id"]
    paper = meta_info["paper"]

    result = summary_structured_llm.invoke([
        SYSTEM_MESSAGE,
        HumanMessage(content=json.dumps(paper, ensure_ascii=False))])
    
    parsed = result.model_dump()
    parsed["id"] = paper_id
    parsed["title"] = paper["title"]

    return {
        "summaries": [parsed],
    }


CONFIRM_YES_ANSWERS = ("yes", "y", "예", "네", "응", "종료", "quit", "q")

# # ---- 유저 선택 ----
def user_select_paper(state: State):
    while True:
        answer = interrupt({
            "summaries": state["summaries"],
            "choice": "Which paper do you like to check?"
            }
        )
        if isinstance(answer, dict) and "choice" in answer:
            choice = answer["choice"]
            break

        # dict가 아닌 응답(예: 문자열)은 선택으로 처리하지 않고 종료 의사를 재확인
        confirm = interrupt({"confirm": "서칭 작업을 완료할까요?"})
        if isinstance(confirm, str) and confirm.strip().lower() in CONFIRM_YES_ANSWERS:
            return {"next_action": "end"}
        # "아니오"면 루프를 돌아 다시 논문 선택 질문을 던짐

    selected_paper = state["summaries"][int(choice) - 1]
    selected_paper['abstract'] = state["papers"][int(choice) - 1]["summary"]
    selected_paper['ai_keywords'] = state["papers"][int(choice) - 1]["ai_keywords"]
    return {
        "selected_id": int(choice) - 1,
        "next_action": "continue",
        "assumption_qna": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            SystemMessage(content=QUE_SYS_PROMPT),
            HumanMessage(content=json.dumps(selected_paper, ensure_ascii=False)),
        ],
    }

def llm_generate_assumption_question(qna_history: list[BaseMessage]) -> str:
    result = llm.invoke(qna_history)
    return result.content

def classify_next_action(answer: str, qna_len_after_answer: int) -> Literal["continue", "switch_paper", "end"]:
    if "다른 논문" in answer or "논문 변경" in answer or "다른 논문 선택" in answer or "next" in answer or "다음 논문" in answer:
        return "switch_paper"
    if "종료" in answer or qna_len_after_answer >= MAX_ASSUMPTION_ROUNDS * 2 + 1 or "quit" in answer:
        return "end"
    return "continue"

# # ---- Agent 2: Assumption Checker (반복 루프) ----
def assumption_checker(state: State):
    qna_history = state["assumption_qna"]
    question = llm_generate_assumption_question(qna_history)
    answer = interrupt(question)
    next_action = classify_next_action(answer, len(qna_history) + 2)
    return {
        "assumption_qna": [AIMessage(content=question), HumanMessage(content=answer)],
        "next_action": next_action,
    }

def should_route_after_select(state: State) -> str:
    if state["next_action"] == "end":
        return END
    return "assumption_checker"

def should_continue_checking(state: State) -> str:
    if state["next_action"] == "continue":
        return "assumption_checker"
    return "save_graph_format"

def should_route_after_save(state: State) -> str:
    if state["next_action"] == "switch_paper":
        return "user_select_paper"
    return END

# # ---- Agent 3: 대화 정리 + Graph ----
MAX_N_KEYWORDS = 8
class ConversationSummary(BaseModel):
    qna_summary: str = Field(
        description="대화의 핵심 내용을 3~5문장으로 요약"
    )

    keywords: list[str] = Field(
        description="핵심 키워드 8개, 짧은 명사구"
    )

keyword_llm = llm.with_structured_output(ConversationSummary)

def extract_keywords(qna_history: list[BaseMessage]) -> list[str]:
    qna_text = "\n".join(f"{m.type}: {m.content}" for m in qna_history[1:])
    result = keyword_llm.invoke([
        SystemMessage(content=QNA_SYSTEM_PROMPT),
        HumanMessage(content=qna_text),
    ])
    return result.model_dump()

def save_graph_format(state: State):
    keywords = extract_keywords(state["assumption_qna"])
    selected_id = state["selected_id"]

    md_path = save_qna_as_markdown(
        state["papers"][selected_id], state["summaries"][selected_id], keywords
    )

    # State에 없으면 디스크에 누적된 그래프를 로드 (State에는 직렬화된 dict로 저장)
    paper_graph = nx.node_link_graph(state["paper_graph"]) if state.get("paper_graph") else load_graph_from_disk()
    keywords_ai = keywords.get("keywords",[])
    if len(keywords_ai)<1:
        keywords_ai = state["papers"][selected_id].get("ai_keywords",[])
    
    if len(keywords_ai)>0:
        keywords_ai = keywords_ai[:MAX_N_KEYWORDS]
        paper_graph = update_graph(paper_graph, state["papers"][selected_id], keywords_ai)
        save_graph_to_disk(paper_graph)  # 종료/논문 전환 전에 디스크에 영속화
        return {"paper_graph": nx.node_link_data(paper_graph)}  # dict로 저장
    return

@tool
def visualize(state: Annotated[dict, InjectedState]):
    """저장된 논문 키워드 그래프를 pyvis로 시각화해 html로 저장합니다."""
    paper_graph = nx.node_link_graph(state["paper_graph"]) if state.get("paper_graph") else load_graph_from_disk()
    visualize_graph(paper_graph)
    return "그래프 시각화를 완료했습니다."

tools = [visualize]
llm_with_tools = llm.bind_tools(tools)

visualize_paper = ToolNode(
    tools=tools,
)

# ---- 0. Triage (LLM, tool-calling으로 visualize 여부 판단) ----
def triage(state: State):
    human_message = HumanMessage(content=state["raw_query"])
    response = llm_with_tools.invoke([human_message])
    return {"messages": [human_message, response]}

def should_route_after_triage(state: State) -> Literal["visualize_paper", "parse_query"]:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "visualize_paper"
    return "parse_query"

# ---- Graph 구성 ----
builder = StateGraph(State)
builder.add_node("triage", triage)
builder.add_node("visualize_paper", visualize_paper)
builder.add_node("parse_query", parse_query)
builder.add_node("fetch_and_score", fetch_and_score)
builder.add_node("summarize_paper", summarize_paper)
builder.add_node("user_select_paper", user_select_paper)
builder.add_node("assumption_checker", assumption_checker)
builder.add_node("save_graph_format", save_graph_format)

builder.add_edge(START, "triage")
builder.add_conditional_edges(
    "triage",
    should_route_after_triage,
    {
        "visualize_paper": "visualize_paper",
        "parse_query": "parse_query",
    },
)
builder.add_edge("visualize_paper", END)
builder.add_edge("parse_query", "fetch_and_score")
builder.add_conditional_edges(
    "fetch_and_score", dispatch_summarizers, ["summarize_paper"]
)
builder.add_edge("summarize_paper", "user_select_paper")
builder.add_conditional_edges(
    "user_select_paper",
    should_route_after_select,
    {
        "assumption_checker": "assumption_checker",
        END: END,
    },
)

builder.add_conditional_edges(
    "assumption_checker",
    should_continue_checking,
    {
        "assumption_checker": "assumption_checker",
        "save_graph_format": "save_graph_format",
    },
)
builder.add_conditional_edges(
    "save_graph_format",
    should_route_after_save,
    {
        "user_select_paper": "user_select_paper",
        END: END,
    },
)

# ---- SqliteSaver 연결 ----
conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(conn)

graph = builder.compile(checkpointer=checkpointer)

# ---- 실행 예시 ----
config = {"configurable": {"thread_id": "session-1"}}
graph.invoke({"raw_query": "최근 한달간 Agent 논문 2개"}, config)

# # ...interrupt 발생 후...
response = {
    "choice": 1,
}
graph.invoke(Command(resume=response), config)
# # ...interrupt 2...
response = "잘모르겠다"
graph.invoke(Command(resume=response), config)

response = "잘모르겠다"
graph.invoke(Command(resume=response), config)

# response = "다음 논문"
# graph.invoke(Command(resume=response), config)

response = "종료"
graph.invoke(Command(resume=response), config)

graph.invoke({"raw_query": "그래프 그림 그려줘"}, config)