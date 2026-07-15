from langchain.chat_models import init_chat_model
from langgraph.types import Command

from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage

from typing import TypedDict, Literal, Optional
from pydantic import BaseModel, Field
from typing_extensions import Annotated

from prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT

RESET_SUMMARIES = "__RESET_SUMMARIES__"
def reset_or_add_summaries(left: list[dict], right: list[dict]) -> list[dict]:
    if right and right[0] == RESET_SUMMARIES:
        return right[1:]
    return left + right

class State(TypedDict):
    messages: Annotated[list, add_messages]

    # sticky routing: 지금 대화가 어떤 에이전트에 "붙잡혀" 있는지
    active_agent: Optional[str]  # None | "assumption_qna" | "graph_query_agent"

    # 논문 서치 관련
    user_request: str
   
    title: str
    topic: str
    start_date: str
    end_date: str
    count: int

    papers: list[dict]
    summaries: Annotated[list[dict], reset_or_add_summaries]

    selected_paper_num: int

    assumption_qna: Annotated[list[BaseMessage], add_messages]
    qna_next_action: Literal["continue", "switch_paper", "end"]

    paper_graph: dict

MAX_ASSUMPTION_ROUNDS = 20  # 무한 루프 방지 하드 리밋

class RouteDecision(BaseModel):
    route: Literal["parse_search_query", "user_select_paper", "respond_directly"]

router_model = init_chat_model("openai:gpt-4o-mini")

def supervisor(state: State) -> Command[Literal["parse_search_query"]]:
    last_user_msg = state["messages"][-1].content if state["messages"] else ""

    if (state.get("active_agent", "") == "assumption_qna") and (state.get("qna_next_action","")=="continue"):
        return Command(
        goto="assumption_qna",
        update={
            "assumption_qna": [HumanMessage(content=last_user_msg)],
        },)
    
    # if (state.get("active_agent", "") == "assumption_qna") and (state.get("qna_next_action","")=="quit"): #temp
    #     return Command(
    #         goto="save_paper",
    #     ) 디버깅용

    summary_exist = "현재 상태 논문 확보 완료" if len( state.get("summaries",[]))>0 else "현재 상태 논문 서치 필요"
    decision = router_model.with_structured_output(RouteDecision).invoke([
        SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT + summary_exist),
        *state["messages"][-4:],
    ])

    if decision.route == "parse_search_query":
        return Command(
        goto="parse_search_query",
        update={
            "user_request": last_user_msg,
        },
    ) 
    return Command(goto=decision.route)
