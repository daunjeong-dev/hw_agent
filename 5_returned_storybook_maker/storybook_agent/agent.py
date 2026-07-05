from google.adk.agents import Agent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from .prompt import ORCHESTRATOR_DESCRIPTION, ORCHESTRATOR_PROMPT
from .sub_agents.story_writer.agent import story_writer_agent
from .sub_agents.sample_maker.agent import sample_maker_agent
from .sub_agents.illustrator.agent import illustrator_agent
from .sub_agents.display.agent import display_agent
from .telemetry_callbacks import log_agent_start, log_tool_start, make_agent_lifecycle_logger
from .context_callbacks import trim_context

MODEL = LiteLlm(model="openai/gpt-4o-mini", parallel_tool_calls=False)

_producer_before, _producer_after = make_agent_lifecycle_logger(
    "그림책 생성 시작", "그림책 생성 완료"
)

storybook_producer = SequentialAgent(
    name="StoryBookProducerAgent",
    sub_agents=[story_writer_agent, sample_maker_agent, illustrator_agent, display_agent],
    description=(
    "Runs StoryWriterAgent → SampleMakerAgent → IllustratorAgent → DisplayAgent in sequence "
    "to produce and present a complete 5-page illustrated storybook."
    ),
    before_agent_callback=_producer_before,
    after_agent_callback=_producer_after,
)

Orchestrator_Agent = Agent(
    name="OrchestratorAgent",
    model=MODEL,
    description=ORCHESTRATOR_DESCRIPTION,
    instruction=ORCHESTRATOR_PROMPT,
    sub_agents=[storybook_producer],
    before_agent_callback=log_agent_start,
    before_model_callback=trim_context,
)

root_agent = Orchestrator_Agent