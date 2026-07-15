import json
from pydantic import BaseModel, Field

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, AIMessage

from agents.supervisor import State, RESET_SUMMARIES
from prompts.summarize_paper import SUMMARY_SYSTEM_PROMPT

class PaperReview(BaseModel):
    rating: float = Field(description="1~5점")

    why_read: str
    why_skip: str

    key_takeaways: list[str]

    application_ideas: list[str]

    summmary: str

llm = init_chat_model("openai:gpt-4o-mini")
SYSTEM_MESSAGE = SystemMessage(content=SUMMARY_SYSTEM_PROMPT)
summary_structured_llm = llm.with_structured_output(PaperReview)
def summarize_paper(meta_info):
    paper_id = meta_info["id"]
    paper = meta_info["paper"]

    result = summary_structured_llm.invoke([
        SYSTEM_MESSAGE,
        AIMessage(content=json.dumps(paper, ensure_ascii=False))])
    
    parsed = result.model_dump()
    parsed["id"] = paper_id
    parsed["title"] = paper["title"]

    return {
        "summaries": [parsed],
    }

def present_summaries(state: State):
    sorted_summaries = sorted(state["summaries"], key=lambda s: s["id"])

    return {
        "summaries": [RESET_SUMMARIES, *sorted_summaries],
        "messages": [AIMessage(content="논문 summary 완료되었습니다.\nassumption qna 를 진행할 논문을 선택해주세요.")],
    }

