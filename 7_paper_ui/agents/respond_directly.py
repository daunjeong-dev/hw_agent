from langchain.chat_models import init_chat_model
from agents.supervisor import State

chat_model = init_chat_model("openai:gpt-4o-mini")
def respond_directly(state: State):
    """기존 에이전트에 해당하지 않는 일반 대화 응답."""
    response = chat_model.invoke(*state["messages"][-4:])
    return {"messages": [response]}