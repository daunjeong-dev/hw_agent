from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.models.lite_llm import LiteLlm
from .prompt import STORYBOOK_PRODUCER_DESCRIPTION, STORYBOOK_PRODUCER_PROMPT
from .sub_agents.story_writer.agent import story_writer_agent
from .sub_agents.sample_maker.agent import sample_maker_agent
from .sub_agents.illustrator.agent import illustrator_agent

MODEL = LiteLlm(model="openai/gpt-4o-mini", parallel_tool_calls=False)

Orchestrator_Agent = Agent(
    name="OrchestratorAgent",
    model=MODEL,
    description=STORYBOOK_PRODUCER_DESCRIPTION,
    instruction=STORYBOOK_PRODUCER_PROMPT,
    tools=[
        AgentTool(agent=story_writer_agent),
        AgentTool(agent=sample_maker_agent),
        AgentTool(agent=illustrator_agent),
    ],
    # before_model_callback=before_model_callback,
)

root_agent = Orchestrator_Agent