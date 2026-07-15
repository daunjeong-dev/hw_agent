from pydantic import BaseModel, Field
from typing import Literal
from langgraph.types import Command

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage
from langgraph.graph import END

from agents.supervisor import State, MAX_ASSUMPTION_ROUNDS

class PaperQnA(BaseModel):
    action: Literal["continue", "switch_paper", "quit"] = Field(description="QnA 계속 진행 or 다른 논문 선택 or 종료")
    user_feedback: str = Field(description="사용자의 답변에 대한 피드백")
    expected_answer: str = Field(description="이전 질문의 모범 답안")
    next_question: str = Field(description="다음 질문")

# # ---- Agent 2: Assumption Checker (반복 루프) ----

qna_llm = init_chat_model("openai:gpt-4o-mini").with_structured_output(PaperQnA)
def assumption_qna(state: State):
    qna_history = state["assumption_qna"]
    question = qna_llm.invoke(qna_history)
    qna_len = len(qna_history)
    
    messages = []
    if question.user_feedback != "":
        messages.append(AIMessage(content="feedback: " + question.user_feedback))

    if question.expected_answer != "":
        messages.append(AIMessage(content="answer: " + question.expected_answer))

    if question.action == "continue":
        messages.append(AIMessage(content="question: " + question.next_question))

    if question.action == "continue" and qna_len < MAX_ASSUMPTION_ROUNDS * 4:
        return Command(
        goto=END,
        update={
            "assumption_qna": messages,
            "qna_next_action": question.action,
            "messages": messages,
        })
    else:
        return Command(
        goto="save_paper",
        update={
            "assumption_qna": messages,
            "qna_next_action": question.action,
            "messages": messages,
        })