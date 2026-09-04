import operator
from typing import Dict, Literal, TypedDict, Optional, List, Annotated, Any
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

# Action Types
NextAction = Literal[
    "DO_NOTHING",
    "SCHEDULE_RETRY",
    "SEND_RESCUE_LINK",
    "SEND_PERSONALIZED_MESSAGE",
    "ESCALATE_TO_SUPPORT",
]

OutcomeType = Literal[
    "RECOVERED",
    "FAILED",
    "PENDING",
    "CANCELLED",
]

ExecutionStatus = Literal[
    "SUCCESS", 
    "FAILED", 
    "PENDING"
]

FailedType = Literal[
    "card_declined",
    "insufficient_funds",
    "expired_card",
    "incorrect_cvc",
    "processing_error",
    "timeout",
    "network_error",
    "fraudulent",
    "other",
]

PreferredChannel = Literal["email", "whatsapp", "sms"]


class CustomerDetails(TypedDict):
    customer_id: str
    email: Optional[str]
    phone: Optional[str]
    plan_name: str
    arpu: float
    tenure_days: int
    failure_count_30d: int
    previous_recoveries: int
    previous_recovery_type: Optional[str]
    preferred_channel: Optional[PreferredChannel]


class ActionRecord(TypedDict):
    timestamp: str
    action_type: NextAction
    execution_status: ExecutionStatus
    gateway_or_provider_response: Dict[str, Any]


class RecoveryAgentState(TypedDict):
    # --- Ingestion Identity & Context ---
    event_id: str
    payment_id: str
    subscription_id: str
    currency: str
    amount_due: float
    failed_type: FailedType
    raw_error_code: Optional[str]
    current_retry_count: int
    customer: CustomerDetails

   
    recovery_score: Optional[int]                    
    baseline_probability: Optional[float]            
    intervention_cost: Optional[float]                # Estimated API / comms cost
    score_breakdown: Optional[Dict[str, int]]         

    # --- Agent Decision (Node: agent_decision) ---
    next_action: Optional[NextAction]
    agent_reasoning: Optional[str]                   
    retry_delay_hours: Optional[int]                 
    generated_message: Optional[str]                 # LLM copy if messaging customer

    # --- Tool Execution Outputs ---
    rescue_link_url: Optional[str]                   # Short URL returned by Razorpay API
    action_history: Annotated[List[ActionRecord], operator.add] 
    recovered_amount: Optional[float]
    outcome: Optional[OutcomeType]

    # --- LangGraph LLM Scratchpad ---
    messages: Annotated[List[AnyMessage], add_messages]