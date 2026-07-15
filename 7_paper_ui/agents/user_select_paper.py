from pydantic import BaseModel, Field
from typing import Literal
from langgraph.types import Send, Command

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from langgraph.graph import END

from agents.supervisor import State
from prompts.user_select_paper import SELECT_PROMPT
from prompts.assumption_qna import QUE_SYS_PROMPT

import json
 
class SelectPaper(BaseModel):
    action: Literal["select", "quit"] = Field(description="논문 선택 or 종료")
    selected_num: int = Field(default=1,description="선택된 논문 번호")

SYSTEM_MESSAGE = SystemMessage(content=SELECT_PROMPT)
llm = init_chat_model("openai:gpt-4o-mini")
def user_select_paper(state: State):
    structured_llm = llm.with_structured_output(SelectPaper)
    result = structured_llm.invoke([
        SYSTEM_MESSAGE,
        *state["messages"][-4:]])
    result = result.model_dump()

    if result.get("action") == "select":
        choice = int(result.get("selected_num", 1))
        selected_paper = state["summaries"][choice-1]
        selected_paper['abstract'] = state["papers"][choice - 1]["summary"]
        selected_paper['ai_keywords'] = state["papers"][choice - 1]["ai_keywords"]    
        return Command(
            goto="assumption_qna",
            update={
                "selected_paper_num": choice,
                "active_agent": "assumption_qna",
                "assumption_status": "continue",
                "assumption_qna": [
                    RemoveMessage(id=REMOVE_ALL_MESSAGES),
                    SystemMessage(content=QUE_SYS_PROMPT),
                    HumanMessage(content=json.dumps(selected_paper, ensure_ascii=False)),
                ],
            },
        )
    else:
        return Command(
            goto=END,
            update={
                "active_agent": None,
            },
        )
