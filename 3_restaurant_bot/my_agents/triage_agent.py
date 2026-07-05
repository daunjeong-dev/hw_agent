import streamlit as st
from agents import (
    Agent,
    RunContextWrapper,
    handoff,
)
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from agents.extensions import handoff_filters
from models import UserAccountContext, HandoffData
from my_agents.menu_agent import menu_agent
from my_agents.order_agent import order_agent
from my_agents.reservation_agent import reservation_agent
from my_agents.complaint_agent import complaint_agent
from my_agents.input_guardrails import off_topic_guardrail
from my_agents.output_guardrails import safety_output_guardrail


def dynamic_triage_agent_instructions(
    wrapper: RunContextWrapper[UserAccountContext],
    agent: Agent[UserAccountContext],
):
    return f"""
{RECOMMENDED_PROMPT_PREFIX}

You are the first point of contact for Restaurant [Outback steakhouse] — a friendly, professional host who greets every guest and routes them to the right specialist.
You call customers by their name.
The customer's name is {wrapper.context.name}.
The customer's phone is {wrapper.context.phone}.

## Role
Understand the customer's intent and hand off to the appropriate agent immediately. Do NOT answer questions yourself.

## Routing Categories
- **MENU** — dishes, ingredients, allergens, dietary options, prices
- **ORDER** — placing, modifying, or canceling an order
- **RESERVATION** — booking, changing, or canceling a table
- **COMPLAINT** — any dissatisfaction, discomfort, or physical service request, including:
  - Food issues (wrong dish, temperature, foreign object)
  - Staff issues (rudeness, slow service)
  - Physical requests requiring staff presence ("식기 바꿔줘", "물 가져다줘", "자리 옮겨줘", "recook my steak")
  - Any sentence expressing frustration or inconvenience
- **OTHER** — compliments, general inquiries → handle briefly yourself

## Behavior
- Greet the customer warmly on first contact
- If intent is ambiguous, ask one clarifying question then route immediately
- When in doubt between OTHER and COMPLAINT, always route to Complaint Agent

## Handoff Rules
- Route immediately once intent is clear
- Never answer menu, order, reservation, or complaint questions yourself

## Tone
Warm, welcoming, efficient. Like a maître d' who makes every guest feel seen.

## Examples
"파스타에 견과류 있나요?" → MENU → Menu Agent
"스테이크 주문할게요" → ORDER → Order Agent  
"식기 바꿔줘" → COMPLAINT → Complaint Agent
"자리 예약하고 싶어요" → RESERVATION → Reservation Agent
"음식이 너무 짜요" → COMPLAINT → Complaint Agent
"""


def handle_handoff(
    wrapper: RunContextWrapper[UserAccountContext],
    input_data: HandoffData,
):

    with st.sidebar:
        st.write(
            f"""
            Handing off to {input_data.to_agent_name}
            Reason: {input_data.reason}
            Issue Type: {input_data.issue_type}
            Description: {input_data.issue_description}
        """
        )


def make_handoff(agent):

    return handoff(
        agent=agent,
        on_handoff=handle_handoff,
        input_type=HandoffData,
        input_filter=handoff_filters.remove_all_tools,
    )


triage_agent = Agent(
    name="Triage Agent",
    instructions=dynamic_triage_agent_instructions,
    input_guardrails=[
        off_topic_guardrail,
    ],
    output_guardrails=[
        safety_output_guardrail
    ],
)

triage_agent.handoffs = [make_handoff(menu_agent), make_handoff(order_agent), make_handoff(reservation_agent), make_handoff(complaint_agent)]
menu_agent.handoffs    = [make_handoff(order_agent), make_handoff(reservation_agent), make_handoff(complaint_agent), make_handoff(triage_agent)]
order_agent.handoffs   = [make_handoff(reservation_agent), make_handoff(complaint_agent), make_handoff(triage_agent)]
reservation_agent.handoffs = [make_handoff(menu_agent), make_handoff(order_agent), make_handoff(complaint_agent), make_handoff(triage_agent)]
complaint_agent.handoffs = [make_handoff(menu_agent), make_handoff(order_agent), make_handoff(reservation_agent), make_handoff(triage_agent)]