from typing import Dict, Any, List , TypedDict, Optional
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import AnyMessage
from pydantic import BaseModel, Field
from backend.app.agent.state import NextAction, RecoveryAgentState
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from dotenv import load_dotenv
load_dotenv()  
import os
class DecisionOutput(BaseModel):
    chosen_action: NextAction = Field(
        description="The chosen action among: DO_NOTHING, SCHEDULE_RETRY, SEND_RESCUE_LINK, SEND_PERSONALIZED_MESSAGE, ESCALATE_TO_SUPPORT."
    )
    agent_reasoning: str = Field(
        description="Concise 1-2 sentence economic justification explaining why this action maximizes net recovered revenue over baseline."
    )
    retry_delay_hours: Optional[int] = Field(
        default=None,
        description="Recommended delay in hours (e.g. 24, 48, 72) if SCHEDULE_RETRY is selected. Otherwise null."
    )
    generated_message: Optional[str] = Field(
        default=None,
        description="Short, friendly, empathetic copy (max 2-3 sentences) if SEND_RESCUE_LINK or SEND_PERSONALIZED_MESSAGE is selected. Never invent facts. Include a placeholder [Payment Link] where the link goes."
    )
    retry_delay_hours: Optional[int] = Field(
        default=None,
        description="Hours to wait if SCHEDULE_RETRY is chosen. Use the precomputed recommendation unless overriding with specific context."
    )
SYSTEM_DECISION_PROMPT = """
You are an Autonomous Revenue Recovery Agent for a SaaS business using Razorpay.
Your objective is to maximize Net Incremental Recovered Revenue.

Guiding Principles:
1. Economic Rationality: Choose the action with the highest positive expected incremental revenue. If doing nothing yields similar or better returns, select DO_NOTHING.
2. Failure Cause Alignment:
   - Expired card or incorrect CVC can NEVER be fixed by retrying. They require customer payment method updates (SEND_RESCUE_LINK or SEND_PERSONALIZED_MESSAGE).
   - Network errors or temporary bank outages usually resolve on their own or via SCHEDULE_RETRY without disturbing the customer.
   - Insufficient funds require empathy and time (allow 24-48 hours or offer alternate payment methods).
3. High-Value Accounts: For high ARPU or long-tenure customers on late retry attempts, human escalation (ESCALATE_TO_SUPPORT) protects retention.
4. Tone: If drafting a message, be concise, polite, and helpful—never accusatory or aggressive.

"""

def agent_decision_node(state: RecoveryAgentState)-> Dict[str,Any]:
    """
    LLM reasoning node that validates the precomputed payoff matrix,
    confirms the final action, provides plain-English reasoning,
    and drafts personalized customer communication if needed.
    """
    llm = ChatGroq(
        model_name="openai/gpt-oss-20b",
        temperature=0.2,
        groq_api_key=os.getenv("GROQ_API_KEY"),
    ).with_structured_output(DecisionOutput)

    customer = state.get("customer", {})
    amount_due = state.get("amount_due", 0.0)
    currency = state.get("currency", "INR")
    failed_type = state.get("failed_type")
    current_retry = state.get("current_retry_count", 1)
    
    recovery_score = state.get("recovery_score", 50)
    baseline_prob = state.get("baseline_probability", 0.0)
    recommended = state.get("recommended_action")
    payoffs = state.get("action_payoffs", [])

    # Format payoffs for readable prompt injection
    payoff_summary = "\n".join([
        f"- {p['action']}: P(recovery)={p['p_recovery']}, Uplift={p['p_uplift']}, Cost={p['intervention_cost']}, E[Incremental Rev]={currency} {p['expected_incremental_revenue']}"
        for p in payoffs
    ])

    user_prompt = f"""
    ### Transaction & Customer Context:
    - Plan: {customer.get('plan_name', 'Subscription')} ({currency} {amount_due})
    - Customer Tenure: {customer.get('tenure_days', 0)} days
    - Failure Type: {failed_type} (Attempt #{current_retry})
    - Preferred Channel: {customer.get('preferred_channel', 'email')}

    ### Pre-Calculated Economic Metrics:
    - Recovery Propensity Score: {recovery_score}/100
    - Baseline Probability (Passive / DO_NOTHING): {baseline_prob}
    - Top Recommended Action by Math Engine: {recommended}
    - Recommended Retry Delay: {state.get('retry_delay_hours')} hours (based on failure type & calendar cycle)

    ### Action Payoff Matrix (Ranked by Expected ROI):
    {payoff_summary}

    Task:
    Confirm or adjust the final action based on context, write a crisp 1-2 sentence economic justification for the dashboard, specify retry hours if scheduling, and draft the message copy if contacting the customer.
    """

    # 3. Invoke LLM
    try:
        decision: DecisionOutput = llm.invoke([
            SystemMessage(content=SYSTEM_DECISION_PROMPT),
            HumanMessage(content=user_prompt)
        ])
    except Exception:
        fallback_action = recommended or "DO_NOTHING"
        fallback_delay = state.get("retry_delay_hours")
        fallback_message = None
        if fallback_action in {"SEND_RESCUE_LINK", "SEND_PERSONALIZED_MESSAGE"}:
            fallback_message = (
                "Your subscription payment could not be completed. "
                "Please update your payment method here: [Payment Link]"
            )
        return {
            "next_action": fallback_action,
            "agent_reasoning": (
                "Used the deterministic recovery recommendation because the LLM decision service was unavailable."
            ),
            "retry_delay_hours": fallback_delay,
            "generated_message": fallback_message,
        }

    return {
        "next_action": decision.chosen_action,
        "agent_reasoning": decision.agent_reasoning,
        "retry_delay_hours": decision.retry_delay_hours,
        "generated_message": decision.generated_message,
    }

    
