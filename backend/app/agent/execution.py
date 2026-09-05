# This node will be responsible for making the decision based on the precomputer payoff matrix and 
import os
import asyncio
import httpx
import logging
from backend.app.agent.state import RecoveryAgentState, ActionRecord
from typing import Dict, Any
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
logger = logging.getLogger(__name__)
load_dotenv()
async def create_razor_paylink(
    amount: float,
    currency: str,
    subscription_id: str,
    payment_id: str,
    customer: Dict[str, Any]
):
    key_id = os.getenv("RAZORPAY_KEY_ID", "rzp_test_sample")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "test_secret")
    if key_id == "rzp_test_sample":
        return f"https://rzp.io/i/mock_rescue_{subscription_id[:8]}"
    # send customer payload to razorpay api to get the link 
    customerPayload= {}
    customer_payload = {}
    if customer.get("name"):
        customer_payload["name"] = customer["name"]
    if customer.get("email"):
        customer_payload["email"] = customer["email"]
    if customer.get("phone"):
        customer_payload["contact"] = customer["phone"]
    payload = {
        "amount": int(round(amount * 100)),  # Convert to smallest currency unit (paise/cents)
        "currency": currency.upper(),
        "accept_partial": False,
        "description": f"Rescue payment for sub #{subscription_id[-8:]}",
        "customer": customer_payload,
        "notify": {
            "sms": bool(customer_payload.get("contact")),
            "email": bool(customer_payload.get("email")),
        },
        "reminder_enable": True,
        "notes": {
            "subscription_id": subscription_id,
            "failed_payment_id": payment_id,
            "rescue_trigger": "agent_auto_recovery",
        },
        # Optional: update to your hackathon app's landing redirect
        # "callback_url": f"https://your-app.com/subscription/recovered?sub_id={subscription_id}",
        # "callback_method": "get",
    }
    try :
        async with httpx.AsyncClient(auth=(key_id, key_secret), timeout=10.0) as client:
            res = await client.post(
                "https://api.razorpay.com/v1/payment_links",
                json=payload
            )
            res.raise_for_status()
            data = res.json()
            return data["short_url"]

    except httpx.HTTPStatusError as exc:
        error_details = exc.response.text
        logger.error(f"Razorpay API error ({exc.response.status_code}): {error_details}")
        raise RuntimeError(f"Failed to create Razorpay link: {error_details}") from exc
    except httpx.RequestError as exc:
        logger.error(f"Network error communicating with Razorpay: {exc}")
        if os.getenv("RAZORPAY_LIVE_LINKS", "false").lower() != "true":
            logger.warning("Using a mock rescue link because RAZORPAY_LIVE_LINKS is not enabled")
            return f"https://rzp.io/i/mock_rescue_{subscription_id[:8]}"
        raise RuntimeError("Razorpay gateway unreachable") from exc
# Now we need to build the 3 nodes for the action of the agent 
async def tool_schedule_retry(state: RecoveryAgentState)-> Dict[str, Any]:
    """ a silent background retry for the failed payment """
    
    delay_hours = state.get("retry_delay_hours") or 24
    retry_time = (datetime.now(timezone.utc) + timedelta(hours=delay_hours)).isoformat()

    record: ActionRecord = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": "SCHEDULE_RETRY",
        "execution_status": "SUCCESS",
        "gateway_or_provider_response": {
            "retry_scheduled_at": retry_time,
            "delay_hours": delay_hours,
        }
    }

    return {
        "action_history": [record],
        "outcome": "PENDING",
    }
async def tool_execute_comms(state: RecoveryAgentState) -> Dict[str, Any]:
    """
    Handles SEND_RESCUE_LINK and SEND_PERSONALIZED_MESSAGE:
    1. Generates the Razorpay payment link.
    2. Injects the link into the LLM's generated message.
    3. Dispatches via WhatsApp or Email.
    """
    customer = state.get("customer", {})
    amount = state.get("amount_due", 0.0)
    currency = state.get("currency", "INR")
    sub_id = state.get("subscription_id", "")
    pay_id = state.get("payment_id", "")
    channel = customer.get("preferred_channel", "email")

    # 1. Create Payment Link
    link_url = await create_razor_paylink(amount, currency, sub_id, pay_id, customer)

    # 2. Inject link into drafted message
    raw_message = state.get("generated_message")
    if raw_message and "[Payment Link]" in raw_message:
        final_message = raw_message.replace("[Payment Link]", link_url)
    elif raw_message:
        final_message = f"{raw_message}\n\nPay here: {link_url}"
    else:
        final_message = f"Your subscription payment of {currency} {amount} failed. Please complete it here: {link_url}"

    # 3. Mock or live dispatch
    provider_message_id = f"msg_{datetime.now(timezone.utc).strftime('%H%M%S')}"

    record: ActionRecord = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": state.get("next_action", "SEND_RESCUE_LINK"),
        "execution_status": "SUCCESS",
        "gateway_or_provider_response": {
            "channel": channel,
            "provider_message_id": provider_message_id,
            "link_url": link_url,
            "message_sent": final_message,
        }
    }

    return {
        "rescue_link_url": link_url,
        "action_history": [record],
        "outcome": "PENDING",
    }


# -------------------------------------------------------------------
# Node 3: Escalate to Support
# -------------------------------------------------------------------
async def tool_escalate(state: RecoveryAgentState) -> Dict[str, Any]:
    """
    Creates an internal support ticket for high-value accounts at churn risk.
    """
    customer = state.get("customer", {})
    amount = state.get("amount_due", 0.0)
    currency = state.get("currency", "INR")
    reasoning = state.get("agent_reasoning", "")

    ticket_id = f"TICKET-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"

    ticket_payload = {
        "ticket_id": ticket_id,
        "customer_id": customer.get("customer_id"),
        "customer_name": customer.get("name", "Subscriber"),
        "amount_due": f"{currency} {amount}",
        "reasoning": reasoning,
        "priority": "HIGH",
    }

    record: ActionRecord = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": "ESCALATE_TO_SUPPORT",
        "execution_status": "SUCCESS",
        "gateway_or_provider_response": ticket_payload,
    }

    return {
        "action_history": [record],
        "outcome": "PENDING",
    }
        
    
