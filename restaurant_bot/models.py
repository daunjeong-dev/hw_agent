from pydantic import BaseModel
from typing import Optional


class UserAccountContext(BaseModel):

    customer_id: int
    name: str
    phone: str
    email: Optional[str] = None

class OrderItem(BaseModel):
    name: str
    quantity: int = 1
    options: str = ""

class ComplaintDetail(BaseModel):
    customer_name: str
    table_number: int
    issue_summary: str
    severity: str  # "low" | "medium" | "high" | "critical"
    incident_time: str = ""
    
class InputGuardRailOutput(BaseModel):

    is_off_topic: bool
    reason: str

class OutputGuardRailOutput(BaseModel):

    is_safe: bool
    reason: str

class HandoffData(BaseModel):

    to_agent_name: str
    issue_type: str
    issue_description: str
    reason: str
