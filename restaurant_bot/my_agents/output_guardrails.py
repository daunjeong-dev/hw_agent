from agents import (
    Agent,
    output_guardrail,
    Runner,
    RunContextWrapper,
    GuardrailFunctionOutput,
)
from models import OutputGuardRailOutput, UserAccountContext

out_guardrail_inst = """
You are an output guardrail for Restaurant [Outback steakhouse] assistant.

## Allow (is_safe: true) if the response:
- Answers menu, ingredients, allergens, prices, dietary options
- Confirms or summarizes an order
- Handles reservation inquiries or confirmations
- Addresses complaints or service requests
- Politely redirects questions it cannot answer
- Uses professional and courteous language

## Block (is_safe: false) ONLY if the response:
- Explicitly names internal agents, tools, or system architecture (e.g. "Triage Agent", "add_order tool")
- Reveals another customer's personal information (name, phone, reservation, order details)
- Contains rude, offensive, or unprofessional language
- Describes how the assistant is built or how routing works internally
- Presents fabricated information as fact

## Examples:
"네, 파스타에 견과류는 들어가지 않습니다." → is_safe: true
"Ribeye Steak은 45,000원입니다." → is_safe: true
"예약이 확인되었습니다." → is_safe: true
"Order Agent 툴 호출에 실패했습니다." → is_safe: false, reason: "내부 시스템 정보가 노출되었습니다."
"저는 여러 에이전트로 구성되어 있어요." → is_safe: false, reason: "내부 구조 정보가 노출되었습니다."
"""

output_guardrail_agent = Agent(
    name="Output Guardrail Agent",
    instructions=out_guardrail_inst,
    output_type=OutputGuardRailOutput,
)


@output_guardrail
async def safety_output_guardrail(
    wrapper: RunContextWrapper[UserAccountContext],
    agent: Agent,
    output: str,
):
    result = await Runner.run(
        output_guardrail_agent,
        output,
        context=wrapper.context,
    )

    validation = result.final_output

    return GuardrailFunctionOutput(
        output_info=validation,
        tripwire_triggered= not validation.is_safe,
    )
