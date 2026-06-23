import streamlit as st
from agents import function_tool, AgentHooks, Agent, Tool, RunContextWrapper
from models import UserAccountContext, OrderItem
from datetime import datetime
import random

@function_tool
def check_availability(context: UserAccountContext, date: str, time: str, party_size: int) -> dict:
    """
    Check available tables for a given date, time, and party size.
    date format: YYYY-MM-DD
    time format: HH:MM
    """
    # Mock data
    available_slots = ["17:00", "17:30", "19:00", "19:30", "21:00"]
    
    requested = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    
    if time in available_slots:
        return {
            "available": True,
            "date": date,
            "time": time,
            "party_size": party_size,
            "table_number": 7
        }
    else:
        return {
            "available": False,
            "date": date,
            "requested_time": time,
            "alternative_slots": available_slots
        }


@function_tool
def create_reservation(
	context: UserAccountContext,
    date: str,
    time: str,
    party_size: int,
    special_request: str = ""
) -> dict:
    """
    Create a table reservation and return a confirmation.
    date format: YYYY-MM-DD
    time format: HH:MM
    """
    # Mock confirmation number
    confirmation_number = f"IW-{date.replace('-', '')}-{context.phone[-4:]}"

    return {
        "success": True,
        "confirmation_number": confirmation_number,
        "customer_name": context.name,
        "phone": context.phone,
        "date": date,
        "time": time,
        "party_size": party_size,
        "table_number": 7,
        "special_request": special_request,
        "message": f"Reservation confirmed for {context.name}, party of {party_size} on {date} at {time}."
    }

@function_tool
def get_menu_items(category: str = "") -> dict:
    """
    Retrieve menu items by category.
    category options: "steak", "pasta", "salad", "dessert", "drinks", "" (all)
    """
    menu = {
        "steak": [
            {
                "name": "Ribeye Steak",
                "price": 45000,
                "description": "12oz 립아이 스테이크, 구운 야채 제공",
                "allergens": ["dairy"],
                "dietary": []
            },
            {
                "name": "Outback Sirloin",
                "price": 38000,
                "description": "8oz 서로인 스테이크, 머쉬룸 소스",
                "allergens": ["dairy", "gluten"],
                "dietary": []
            },
        ],
        "pasta": [
            {
                "name": "Creamy Mushroom Pasta",
                "price": 22000,
                "description": "크리미 머쉬룸 소스 페투치네",
                "allergens": ["gluten", "dairy", "eggs"],
                "dietary": ["vegetarian"]
            },
            {
                "name": "Grilled Chicken Pasta",
                "price": 24000,
                "description": "그릴드 치킨, 토마토 바질 소스 스파게티",
                "allergens": ["gluten"],
                "dietary": []
            },
        ],
        "salad": [
            {
                "name": "Caesar Salad",
                "price": 15000,
                "description": "로메인, 파마산, 크루통, 시저 드레싱",
                "allergens": ["gluten", "dairy", "eggs", "fish"],
                "dietary": ["vegetarian"]
            },
        ],
        "dessert": [
            {
                "name": "Chocolate Thunder",
                "price": 12000,
                "description": "웜 초콜릿 케이크, 바닐라 아이스크림",
                "allergens": ["gluten", "dairy", "eggs", "nuts"],
                "dietary": ["vegetarian"]
            },
        ],
        "drinks": [
            {
                "name": "Lemonade",
                "price": 7000,
                "description": "직접 만든 레모네이드",
                "allergens": [],
                "dietary": ["vegan", "gluten-free"]
            },
        ],
    }

    if category and category in menu:
        return {"category": category, "items": menu[category]}
    
    return {"category": "all", "items": menu}


@function_tool
def check_allergens(dish_name: str, allergen: str) -> dict:
    """
    Check if a specific dish contains a given allergen.
    allergen options: "gluten", "dairy", "nuts", "eggs", "soy", "shellfish", "fish"
    """
    allergen_db = {
        "Ribeye Steak":          ["dairy"],
        "Outback Sirloin":       ["dairy", "gluten"],
        "Creamy Mushroom Pasta": ["gluten", "dairy", "eggs"],
        "Grilled Chicken Pasta": ["gluten"],
        "Caesar Salad":          ["gluten", "dairy", "eggs", "fish"],
        "Chocolate Thunder":     ["gluten", "dairy", "eggs", "nuts"],
        "Lemonade":              [],
    }

    dish_allergens = allergen_db.get(dish_name)

    if dish_allergens is None:
        return {
            "found": False,
            "message": f"'{dish_name}' 메뉴를 찾을 수 없습니다. 메뉴명을 확인해주세요."
        }

    contains = allergen in dish_allergens

    return {
        "found": True,
        "dish_name": dish_name,
        "allergen": allergen,
        "contains": contains,
        "all_allergens": dish_allergens,
        "message": (
            f"⚠️ {dish_name}에 {allergen}이 포함되어 있습니다. 섭취에 주의하세요."
            if contains else
            f"✅ {dish_name}에 {allergen}이 포함되어 있지 않습니다."
        )
    }

price_db = {
    "Ribeye Steak": 45000,
    "Outback Sirloin": 38000,
    "Creamy Mushroom Pasta": 22000,
    "Grilled Chicken Pasta": 24000,
    "Caesar Salad": 15000,
    "Chocolate Thunder": 12000,
    "Lemonade": 7000,
}
if "order_store" not in st.session_state:
    st.session_state["order_store"] = {}
order_store = st.session_state["order_store"]

@function_tool
def add_order(
    context: UserAccountContext,
    table_number: int,
    items: list[OrderItem],
    special_request: str = ""
) -> dict:
    """
    Place a new order for a table.
    items format: [OrderItem(name="Ribeye Steak", quantity=2, options="medium-well")]
    """
    if not items:
        return {
            "success": False,
            "message": "주문 항목이 없습니다. 메뉴를 선택해주세요."
        }

    order_items = []
    total_price = 0

    for item in items:
        unit_price = price_db.get(item.name)

        if unit_price is None:
            return {
                "success": False,
                "message": f"'{item.name}' 메뉴를 찾을 수 없습니다. 메뉴명을 확인해주세요."
            }

        subtotal = unit_price * item.quantity
        total_price += subtotal

        order_items.append({
            "name": item.name,
            "quantity": item.quantity,
            "options": item.options,
            "unit_price": unit_price,
            "subtotal": subtotal
        })

    order_number = f"ORD-{datetime.now().strftime('%H%M%S')}-{random.randint(10,99)}"
    estimated_minutes = 15 + (len(order_items) * 3)

    order_store[order_number]={
        "customer_name": context.name,
        "table_number": table_number,
        "items": order_items,
        "total_price": total_price,
        "special_request": special_request,
        "status": "preparing",
        "created_at": datetime.now().isoformat()
    }

    return {
        "success": True,
        "order_number": order_number,
        "customer_name": context.name,
        "table_number": table_number,
        "items": order_items,
        "total_price": total_price,
        "special_request": special_request,
        "estimated_time": f"{estimated_minutes}분",
        "message": f"주문이 접수되었습니다. 예상 대기시간은 약 {estimated_minutes}분입니다."
    }


@function_tool
def cancel_order(order_number: str, reason: str = "") -> dict:
    """
    Cancel an existing order by order number.
    """

    order = order_store.get(order_number)

    if not order:
        return {
            "success": False,
            "message": f"'{order_number}' 주문을 찾을 수 없습니다. 주문 번호를 확인해주세요."
        }

    if order["status"] == "completed":
        return {
            "success": False,
            "order_number": order_number,
            "message": "이미 완료된 주문은 취소할 수 없습니다. 직원에게 문의해주세요."
        }

    if order["status"] == "served":
        return {
            "success": False,
            "order_number": order_number,
            "message": "이미 서빙된 주문은 취소할 수 없습니다. 직원에게 문의해주세요."
        }
    
    order_store[order_number]["status"] = "cancelled"
    order_store[order_number]["cancelled_at"] = datetime.now().isoformat()
    order_store[order_number]["cancel_reason"] = reason

    return {
        "success": True,
        "order_number": order_number,
        "customer_name": order["customer_name"],
        "table_number": order["table_number"],
        "cancelled_items": order["items"],
        "refund_amount": order["total_price"],
        "reason": reason,
        "message": f"주문 {order_number}이 취소되었습니다. 환불 금액은 {order['total_price']:,}원입니다."
    }

class AgentToolUsageLoggingHooks(AgentHooks):

    async def on_tool_start(
        self,
        context: RunContextWrapper[UserAccountContext],
        agent: Agent[UserAccountContext],
        tool: Tool,
    ):
        with st.sidebar:
            st.write(f"?? **{agent.name}** starting tool: `{tool.name}`")

    async def on_tool_end(
        self,
        context: RunContextWrapper[UserAccountContext],
        agent: Agent[UserAccountContext],
        tool: Tool,
        result: str,
    ):
        with st.sidebar:
            st.write(f"?? **{agent.name}** used tool: `{tool.name}`")
            st.code(result)

    async def on_handoff(
        self,
        context: RunContextWrapper[UserAccountContext],
        agent: Agent[UserAccountContext],
        source: Agent[UserAccountContext],
    ):
        with st.sidebar:
            st.write(f"?? Handoff: **{source.name}** �� **{agent.name}**")

    async def on_start(
        self,
        context: RunContextWrapper[UserAccountContext],
        agent: Agent[UserAccountContext],
    ):
        with st.sidebar:
            st.write(f"?? **{agent.name}** activated")

    async def on_end(
        self,
        context: RunContextWrapper[UserAccountContext],
        agent: Agent[UserAccountContext],
        output,
    ):
        with st.sidebar:
            st.write(f"?? **{agent.name}** completed")
