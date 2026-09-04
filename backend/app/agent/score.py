# choose to calculate in manually cause feeding Into LLM will cause the hallucination error and will use a lot of tokens so that's why we are calculating it manually 
from typing import Dict, Any, List, TypedDict
from backend.app.agent.state import RecoveryAgentState, NextAction

from datetime import datetime
class ActionPayoff(TypedDict):
    action: NextAction
    p_recovery: float
    p_uplift: float
    intervention_cost: float
    expected_incremental_revenue: float
    is_viable: bool
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
        "SEND_RESCUE_LINK": 0.60,
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


from datetime import datetime

def calculate_recommended_retry_delay(
    failed_type: str,
    failure_code: str | None,
    attempt_number: int,
) -> int | None:
    """
    Computes optimal retry delay in hours based on clearing cycles.
    Returns None if retrying is physically futile (e.g., expired card).
    """
    failure_code = (failure_code or "").upper()

    # 1. Unretryable Hard Failures
    if failed_type in {"expired_card", "incorrect_cvc", "fraudulent"}:
        return None
    
    # 2. Transient Technical Issues (Bank switch outages clear quickly)
    if failed_type in {"network_error", "timeout", "processing_error"} or failure_code in {
        "GATEWAY_ERROR", "NETWORK_ERROR", "BANK_SYSTEM_OUTAGE"
    }:
        return 4 if attempt_number == 1 else 8

    # 3. Liquidity / Insufficient Funds (Salary cycle vs mid-month)
    if failed_type == "insufficient_funds" or failure_code in {"INSUFFICIENT_FUNDS", "LIMIT_EXCEEDED"}:
        day_of_month = datetime.now().day
        # Around salary window (28th to 5th): fast replenishment
        if day_of_month >= 28 or day_of_month <= 5:
            return 24 if attempt_number == 1 else 48
        # Mid-month: accounts need more time to be funded
        return 48 if attempt_number == 1 else 72

    # 4. Generic Card Decline (Cooldown for velocity / daily fraud rules)
    if attempt_number == 1:
        return 24
    elif attempt_number == 2:
        return 48
    else:
        return 72
def compute_score(state: RecoveryAgentState)-> Dict[str,Any]:
    failed_type = state["failed_type"]
    failure_code = state.get("raw_error_code") or state.get("failure_code")
    attempt_number = state.get("current_retry_count", 1)
    customer = state.get("customer", {})
    amount_due = state.get("amount_due", 0.0)
    score= 50
    failure_class = classify_failure(failed_type, failure_code)
    if failure_class == "HARD":
        factor = -45.0
    elif failure_class == "TEMPORARY":
        factor = 20.0
    elif failed_type == "insufficient_funds":
        factor = 10.0
    elif failed_type == "expired_card":
        factor = -10.0  # Needs user link, but customer intent remains intact
    elif failed_type in {"incorrect_cvc", "card_declined"}:
        factor = -10.0
    else:
        factor = -5.0
    score += factor
    attempt_factors = {1: 10.0, 2: 0.0, 3: -15.0}
    attempt_factor = attempt_factors.get(attempt_number, -30.0)
    score += attempt_factor
    attempt_factors = {1: 10.0, 2: 0.0, 3: -15.0}
    attempt_factor = attempt_factors.get(attempt_number, -30.0)
    
    score += attempt_factor

    # 3. Customer tenure
    tenure_days = customer.get("tenure_days", 0)
    if tenure_days >= 180:
        tenure_factor = 15.0
    elif tenure_days >= 60:
        tenure_factor = 8.0
    elif tenure_days >= 30:
        tenure_factor = 0.0
    else:
        tenure_factor = -8.0
  
    score += tenure_factor

    # 4. Historical payment behavior
    successful_payments = customer.get("successful_payments", 0)
    if successful_payments >= 12:
        payment_factor = 12.0
    elif successful_payments >= 6:
        payment_factor = 7.0
    elif successful_payments >= 2:
        payment_factor = 2.0
    else:
        payment_factor = -5.0

    score += payment_factor

    # 5. Prior recoveries track record
    previous_recoveries = customer.get("previous_recoveries", 0)
    if previous_recoveries >= 3:
        recovery_factor = 10.0
    elif previous_recoveries >= 1:
        recovery_factor = 5.0
    else:
        recovery_factor = 0.0
  
    score += recovery_factor

    # 6. Failure count in past 30 days
    failures_30d = customer.get("failure_count_30d", 0)
    if failures_30d == 0:
        fail_factor = 5.0
    elif failures_30d == 1:
        fail_factor = 0.0
    elif failures_30d <= 3:
        fail_factor = -8.0
    else:
        fail_factor = -18.0
 
    score += fail_factor

    # 7. Recency of last payment
    last_successful_days = customer.get("last_successful_payment_days_ago")
    if last_successful_days is not None:
        if last_successful_days <= 7:
            recency_factor = 8.0
        elif last_successful_days <= 30:
            recency_factor = 4.0
        elif last_successful_days <= 90:
            recency_factor = 0.0
        else:
            recency_factor = -5.0
        # breakdown["recent_payment_activity"] = recency_factor
        score += recency_factor

    # 8. Subscription tier / ARPU
    if amount_due >= 10000:
        arpu_factor = 10.0
    elif amount_due >= 2000:
        arpu_factor = 5.0
    else:
        arpu_factor = 0.0
    
    score += arpu_factor

    # 9. Hard safety ceiling for fraudulent activities
    if failure_class == "HARD":
        score = min(score, 15.0)

    final_score = int(max(0.0, min(100.0, score)))
    return final_score
def compute_baseline_probability(state:RecoveryAgentState)-> float:
    failed_type = state["failed_type"]
    failure_code = state.get("raw_error_code") or state.get("failure_code")
    attempt_number = state.get("current_retry_count", 1)
    failure_class= classify_failure(failed_type, failure_code)
    if failure_class == "HARD" or failed_type in {"expired_card", "incorrect_cvc", "card_declined"} or attempt_number >= 4:
        return 0.0
    if failed_type in TEMPORARY_FAILURES:
        base_probability = 0.75
    elif failed_type == "insufficient_funds":
        base_probability = 0.35
    elif failed_type == "card_declined":
        base_probability = 0.15
    else:
        base_probability = 0.10
    attempt_multiplier = {1: 1.00, 2: 0.50, 3: 0.15}.get(attempt_number, 0.00)
    probability = base_probability * attempt_multiplier
    customer = state.get("customer",{})
    successful_payments = customer.get("successful_payments", 0)
    previous_recoveries = customer.get("previous_recoveries", 0)

    if successful_payments >= 12:
        probability *= 1.10
    elif successful_payments >= 6:
        probability *= 1.05

    if previous_recoveries >= 3:
        probability *= 1.10
    elif previous_recoveries >= 1:
        probability *= 1.05

    # Timing signal for liquidity/balance issues
    if failed_type == "insufficient_funds":
        current_day = datetime.now().day
        if current_day >= 28 or current_day <= 5:
            probability *= 1.20
        elif 10 <= current_day <= 25:
            probability *= 0.90

    return round(max(0.00, min(0.90, probability)), 2)
def get_action_cost(action: NextAction, channel: str = "whatsapp") -> float:
    """Tangible infrastructure/API charges + intangible fatigue costs."""
    if action == "DO_NOTHING":
        return 0.0
    if action == "SCHEDULE_RETRY":
        return 2.0
    if action == "SEND_RESCUE_LINK":
        return 3.5 if channel == "whatsapp" else 1.0
    if action == "SEND_PERSONALIZED_MESSAGE":
        return 8.0 if channel == "whatsapp" else 2.5
    if action == "ESCALATE_TO_SUPPORT":
        return 150.0  # Human CS rep overhead
    return 5.0
def evaluate_action_payoffs(
    recovery_score: int,
    baseline_prob: float,
    amount_due: float,
    failed_type: str,
    channel: str,
) -> List[ActionPayoff]:
    """Calculates Net Expected Incremental Revenue for all actions."""
    affinities = AFFINITY_MATRIX.get(failed_type, DEFAULT_AFFINITY)
    actions: List[NextAction] = [
        "DO_NOTHING",
        "SCHEDULE_RETRY",
        "SEND_RESCUE_LINK",
        "SEND_PERSONALIZED_MESSAGE",
        "ESCALATE_TO_SUPPORT",
    ]

    payoffs: List[ActionPayoff] = []

    for action in actions:
        cost = get_action_cost(action, channel=channel)

        if action == "DO_NOTHING":
            p_action = baseline_prob
            uplift = 0.0
            expected_incremental_rev = 0.0
        else:
            affinity = affinities.get(action, 0.40)
            if affinity == 0.0:
                p_action = 0.0
            else:
                p_action = round(min(0.95, (recovery_score / 100.0) * affinity), 3)

            uplift = round(max(0.0, p_action - baseline_prob), 3)
            # E[Incremental Rev] = (P_action - P_baseline) * Amount - Cost
            expected_incremental_rev = round((uplift * amount_due) - cost, 2)

        payoffs.append(
            ActionPayoff(
                action=action,
                p_recovery=p_action,
                p_uplift=uplift,
                intervention_cost=cost,
                expected_incremental_revenue=expected_incremental_rev,
                is_viable=expected_incremental_rev > 0 or action == "DO_NOTHING",
            )
        )

    # Sort descending by Expected Incremental Revenue
    payoffs.sort(key=lambda x: x["expected_incremental_revenue"], reverse=True)
    return payoffs
def compute_scores_node(state: RecoveryAgentState) -> Dict[str, Any]:
    """
    Unified scoring node. Executes all deterministic calculations 
    and updates the state for the LLM agent decision node.
    """
    recovery_score, score_breakdown = compute_score(state)
    baseline_probability = compute_baseline_probability(state)

    customer = state.get("customer", {})
    preferred_channel = customer.get("preferred_channel", "whatsapp")
    amount_due = state.get("amount_due", 0.0)
    failed_type = state.get("failed_type", "other")
    failure_code = state.get("raw_error_code") or state.get("failure_code")
    attempt_number = state.get("current_retry_count", 1)

    # Evaluate expected revenue across all options
    payoff_matrix = evaluate_action_payoffs(
        recovery_score=recovery_score,
        baseline_prob=baseline_probability,
        amount_due=amount_due,
        failed_type=failed_type,
        channel=preferred_channel,
    )
    recommended_delay = calculate_recommended_retry_delay(
        failed_type=failed_type,
        failure_code=failure_code,
        attempt_number=attempt_number,
    ) 

    best_action_data = payoff_matrix[0]

    return {
        "recovery_score": recovery_score,
        "baseline_probability": baseline_probability,
        "score_breakdown": score_breakdown,
        "action_payoffs": payoff_matrix,
        "recommended_action": best_action_data["action"],
        "recommended_delay": recommended_delay,
        "intervention_cost": best_action_data["intervention_cost"],
    }
    
    

    
    
    
    
    