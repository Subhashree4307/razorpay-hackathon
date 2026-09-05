from pydantic import BaseModel, Field
from typing import Optional
from backend.app.agent.state import FailedType
class SimulationRequest(BaseModel):
    plan_name: str = Field(default="Pro Monthly")
    amount_due: float = Field(default=4999.0)
    failed_type: FailedType = Field(default="expired_card")
    raw_error_code: Optional[str] = Field(default="EXPIRED_CARD")
    current_retry_count: int = Field(default=1)
    customer_name: str = Field(default="Arjun Mehta")
    customer_email: str = Field(default="arjun@example.com")
    customer_phone: str = Field(default="+919876543210")
    preferred_channel: str = Field(default="whatsapp")
    tenure_days: int = Field(default=120)
    successful_payments: int = Field(default=4)