# choose to calculate in manually cause feeding Into LLM will cause the hallucination error and will use a lot of tokens so that's why we are calculating it manually 
from typing import Dict, Any
from backend.app.agent.state import RecoveryAgentState
TEMPORARY_FAILURES = {
    "network_error",
    "timeout",
    "processing_error",
}
FIXABLE_FAILURES = {
    "expired_card",
    "incorrect_cvc",
    "card_declined",
    "insufficient_funds",
}
HARD_FAILURES = {
    "fraudulent",
}
DEFAULT_AFFINITY = {
    "SCHEDULE_RETRY": 0.40,
    "SEND_RESCUE_LINK": 0.70,
    "SEND_PERSONALIZED_MESSAGE": 0.75,
    "ESCALATE_TO_SUPPORT": 0.40,
}
AFFINITY_MATRIX: Dict[str, Dict[str, float]] = {
    "network_error": {
        "SCHEDULE_RETRY": 0.95,
        "SEND_RESCUE_LINK": 0.50,
        "SEND_PERSONALIZED_MESSAGE": 0.40,
        "ESCALATE_TO_SUPPORT": 0.10,
    },
    "insufficient_funds": {
        "SCHEDULE_RETRY": 0.75,
        "SEND_RESCUE_LINK": 0.70,
        "SEND_PERSONALIZED_MESSAGE": 0.85,
        "ESCALATE_TO_SUPPORT": 0.40,
    },
    "expired_card": {
        "SCHEDULE_RETRY": 0.0,   
        "SEND_RESCUE_LINK": 0.85,
        "SEND_PERSONALIZED_MESSAGE": 0.90,
        "ESCALATE_TO_SUPPORT": 0.75,
    },
    "incorrect_cvc": {
        "SCHEDULE_RETRY": 0.0,
        "SEND_RESCUE_LINK": 0.85,
        "SEND_PERSONALIZED_MESSAGE": 0.90,
        "ESCALATE_TO_SUPPORT": 0.60,
    },
    "card_declined": {
        "SCHEDULE_RETRY": 0.30,
        "SEND_RESCUE_LINK": 0.80,
        "SEND_PERSONALIZED_MESSAGE": 0.82,
        "ESCALATE_TO_SUPPORT": 0.60,
    },
    "fraudulent": {
        "SCHEDULE_RETRY": 0.0,
        "SEND_RESCUE_LINK": 0.0,
        "SEND_PERSONALIZED_MESSAGE": 0.0,
        "ESCALATE_TO_SUPPORT": 0.0,
    },
}
def classify_failure(failed_type:str, failure_code:str)->str:
    if (
        failed_type in HARD_FAILURES
        or failure_code in {"FRAUD", "FRAUDULENT", "ACCOUNT_CLOSED", "STOLEN_CARD"}
    ):
        return "HARD"

    if failed_type in TEMPORARY_FAILURES or failure_code in {
        "GATEWAY_ERROR",
        "NETWORK_ERROR",
        "BANK_SYSTEM_OUTAGE",
    }:
        return "TEMPORARY"

    if failed_type in FIXABLE_FAILURES or failure_code in {
        "INSUFFICIENT_FUNDS",
        "LIMIT_EXCEEDED",
        "CARD_BLOCKED",
        "EXPIRED_CARD",
        "INVALID_CVC",
    }:
        return "FIXABLE"
    return "UNKNOWN"
def compute_score(state: RecoveryAgentState)-> Dict[str,Any]:
    failed_type = state["failed_type"]
    failure_code = state.get("raw_error_code") or state.get("failure_code")
    attempt_number = state.get("current_retry_count", 1)
    customer = state.get("customer", {})
    amount_due = state.get("amount_due", 0.0)
    basescore= 50
    failure_class = classify_failure(failed_type, failure_code)
    
    
    