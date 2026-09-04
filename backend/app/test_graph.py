# test_graph.py
import asyncio
from pprint import pprint
import sys
from pathlib import Path

# Add 'backend' directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.graph import recovery_graph
# Scenario 1: Expired Card -> Should trigger SEND_RESCUE_LINK / SEND_PERSONALIZED_MESSAGE
scenario_expired_card = {
    "event_id": "evt_test_01",
    "payment_id": "pay_test_01",
    "subscription_id": "sub_test_01",
    "currency": "INR",
    "amount_due": 4999.0,
    "failed_type": "expired_card",
    "raw_error_code": "EXPIRED_CARD",
    "current_retry_count": 1,
    "customer": {
        "customer_id": "cust_001",
        "name": "Arjun Mehta",
        "email": "arjun@example.com",
        "phone": "+919876543210",
        "plan_name": "Pro Monthly",
        "arpu": 4999.0,
        "tenure_days": 120,
        "failure_count_30d": 0,
        "successful_payments": 4,
        "previous_recoveries": 1,
        "preferred_channel": "whatsapp",
    },
    "action_history": [],
}

# Scenario 2: Network Timeout -> Should trigger DO_NOTHING or SCHEDULE_RETRY (high baseline)
scenario_network_timeout = {
    "event_id": "evt_test_02",
    "payment_id": "pay_test_02",
    "subscription_id": "sub_test_02",
    "currency": "INR",
    "amount_due": 499.0,
    "failed_type": "network_error",
    "raw_error_code": "GATEWAY_ERROR",
    "current_retry_count": 1,
    "customer": {
        "customer_id": "cust_002",
        "name": "Priya Sharma",
        "email": "priya@example.com",
        "phone": "+919876543211",
        "plan_name": "Starter Tier",
        "arpu": 499.0,
        "tenure_days": 40,
        "failure_count_30d": 0,
        "successful_payments": 1,
        "previous_recoveries": 0,
        "preferred_channel": "email",
    },
    "action_history": [],
}

# Scenario 3: High Value Account at Risk -> Should trigger ESCALATE_TO_SUPPORT
scenario_enterprise_risk = {
    "event_id": "evt_test_03",
    "payment_id": "pay_test_03",
    "subscription_id": "sub_test_03",
    "currency": "INR",
    "amount_due": 65000.0,
    "failed_type": "card_declined",
    "raw_error_code": "DO_NOT_HONOR",
    "current_retry_count": 3,
    "customer": {
        "customer_id": "cust_003",
        "name": "Enterprise Client X",
        "email": "billing@enterprisex.com",
        "phone": "+919876543212",
        "plan_name": "Enterprise Annual",
        "arpu": 65000.0,
        "tenure_days": 400,
        "failure_count_30d": 2,
        "successful_payments": 14,
        "previous_recoveries": 2,
        "preferred_channel": "email",
    },
    "action_history": [],
}

async def run_tests():
    scenarios = [
        ("EXPIRED CARD SCENARIO", scenario_expired_card),
        ("TRANSIENT NETWORK OUTAGE SCENARIO", scenario_network_timeout),
        ("ENTERPRISE CHURN RISK SCENARIO", scenario_enterprise_risk),
    ]

    for title, state in scenarios:
        print(f"\n{'='*20} {title} {'='*20}")
        final_state = await recovery_graph.ainvoke(state)
        
        print(f"Propensity Score   : {final_state.get('recovery_score')}/100")
        print(f"Baseline Prob      : {final_state.get('baseline_probability')}")
        print(f"Recommended Action : {final_state.get('recommended_action')}")
        print(f"Final Chosen Action: {final_state.get('next_action')}")
        print(f"Agent Reasoning    : {final_state.get('agent_reasoning')}")
        if final_state.get("rescue_link_url"):
            print(f"Rescue Link        : {final_state.get('rescue_link_url')}")
        if final_state.get("retry_delay_hours"):
            print(f"Retry Delay        : {final_state.get('retry_delay_hours')} hours")
        print("Action History:")
        pprint(final_state.get("action_history"))

if __name__ == "__main__":
    asyncio.run(run_tests())