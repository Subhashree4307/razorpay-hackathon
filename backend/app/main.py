from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from app.agent.graph import recovery_graph
from app.agent.state import RecoveryAgentState, FailedType
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
from app.schema import SimulationRequest
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid
import os 
import logging
from pymongo.errors import PyMongoError
from dotenv import load_dotenv
import certifi

logger = logging.getLogger(__name__)
load_dotenv()
MONGODB_URL = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "razorpay_hackathon")
mongo_client: AsyncIOMotorClient = None
db: Optional[Any] = None
@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, db
    mongo_client = AsyncIOMotorClient(
        MONGODB_URL,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    db = mongo_client[DATABASE_NAME]

    try:
        await db["recovery_events"].create_index("event_id", unique=True)
        await db["recovery_events"].create_index([("timestamp", -1)])
    except PyMongoError as exc:
        logger.warning("MongoDB unavailable; recovery records will not be persisted: %s", exc)
        db = None

    yield

    if mongo_client:
        mongo_client.close()

app = FastAPI(
    title= "Autonomous Payment Recovery Agent", 
    description= "Agentic dunning and revenue optimization powered by LangGraph",
    version= "1.0.0",
    lifespan=lifespan,
) 
# for the enabling of Cors 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

async def process_failed_payment(intial_state: RecoveryAgentState)-> Dict[str, Any]:
    # Run the Recovery Graph to determine the next action and reasoning
    final_state= await recovery_graph.ainvoke(intial_state)
    record= {
        "event_id": final_state.get("event_id"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "subscription_id": final_state.get("subscription_id"),
        "payment_id": final_state.get("payment_id"),
        "amount_due": final_state.get("amount_due"),
        "currency": final_state.get("currency", "INR"),
        "failed_type": final_state.get("failed_type"),
        "customer": final_state.get("customer"),
        "recovery_score": final_state.get("recovery_score"),
        "baseline_probability": final_state.get("baseline_probability"),
        "recommended_action": final_state.get("recommended_action"),
        "chosen_action": final_state.get("next_action"),
        "agent_reasoning": final_state.get("agent_reasoning"),
        "rescue_link_url": final_state.get("rescue_link_url"),
        "retry_delay_hours": final_state.get("retry_delay_hours"),
        "action_history": final_state.get("action_history", []),
        "status": final_state.get("outcome", "PENDING"),
    }
    if db is not None:
        try:
            await db["recovery_events"].insert_one(record)
        except PyMongoError as exc:
            logger.warning("Could not persist recovery event %s: %s", record["event_id"], exc)
    record_copy= dict(record)
    record_copy.pop("_id", None)
    return record_copy
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "recovery-agent"}


@app.get("/api/recoveries")
async def get_all_recoveries(limit: int = 50, skip: int = 0):
    """Returns all processed recovery events sorted newest first from MongoDB."""
    if db is None:
        raise HTTPException(status_code=503, detail="Recovery database unavailable")

    events_cursor = (
        db["recovery_events"]
        .find({}, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )
    events = await events_cursor.to_list(length=limit)
    total_events = await db["recovery_events"].count_documents({})

    return {
        "total_events": total_events,
        "events": events,
    }
@app.post("/api/test/simulate-failure")
async def simulate_failure(payload: SimulationRequest):
    """
    Convenience endpoint for UI / manual testing.
    Constructs state and executes the agent pipeline synchronously.
    """
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    sub_id = f"sub_{uuid.uuid4().hex[:8]}"
    pay_id = f"pay_{uuid.uuid4().hex[:8]}"

    state: RecoveryAgentState = {
        "event_id": event_id,
        "payment_id": pay_id,
        "subscription_id": sub_id,
        "currency": "INR",
        "amount_due": payload.amount_due,
        "failed_type": payload.failed_type,
        "raw_error_code": payload.raw_error_code,
        "current_retry_count": payload.current_retry_count,
        "customer": {
            "customer_id": f"cust_{uuid.uuid4().hex[:6]}",
            "name": payload.customer_name,
            "email": payload.customer_email,
            "phone": payload.customer_phone,
            "plan_name": payload.plan_name,
            "arpu": payload.amount_due,
            "tenure_days": payload.tenure_days,
            "failure_count_30d": 0,
            "successful_payments": payload.successful_payments,
            "previous_recoveries": 1,
            "preferred_channel": payload.preferred_channel,
        },
        "action_history": [],
    }

    result = await process_failed_payment(state)
    return {
        "status": "success",
        "data": result,
    }


async def mark_payment_recovered(payment_entity: Dict[str, Any], event_id: str) -> int:
    """Mark the failed event as recovered after Razorpay confirms capture."""
    if db is None:
        raise HTTPException(status_code=503, detail="Recovery database unavailable")

    payment_id = payment_entity.get("id")
    failed_payment_id = payment_entity.get("notes", {}).get("failed_payment_id")
    lookup_ids = [value for value in (payment_id, failed_payment_id) if value]
    if not lookup_ids:
        return 0

    result = await db["recovery_events"].update_many(
        {"payment_id": {"$in": lookup_ids}},
        {
            "$set": {
                "status": "RECOVERED",
                "recovered_amount": float(payment_entity.get("amount", 0)) / 100.0,
                "recovered_at": datetime.now(timezone.utc).isoformat(),
                "recovery_event_id": event_id,
            }
        },
    )
    return result.modified_count


@app.post("/api/webhook/razorpay")
async def razorpay_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Production entrypoint: handles incoming Razorpay webhooks.
    Filters for subscription.charged (failed) and payment.failed.
    """
    payload = await request.json()
    event_type = payload.get("event")

    if event_type == "payment.captured":
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        updated_count = await mark_payment_recovered(payment_entity, payload.get("id", ""))
        return {
            "status": "processed",
            "recovered_events": updated_count,
        }

    # Filter for subscription failure events
    if event_type not in ["payment.failed", "subscription.charged"]:
        return {"status": "ignored", "reason": f"Event {event_type} is not a payment failure"}

    # Extract payment entity
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    sub_id = payment_entity.get("subscription_id") or "sub_demo_direct"
    pay_id = payment_entity.get("id") or f"pay_{uuid.uuid4().hex[:8]}"
    amount = float(payment_entity.get("amount", 0)) / 100.0  # Razorpay sends paise
    raw_error = payment_entity.get("error_code", "GENERIC_DECLINE")

    # Normalize error code into FailedType
    failed_type: FailedType = "card_declined"
    if "EXPIRED" in raw_error:
        failed_type = "expired_card"
    elif "FUNDS" in raw_error:
        failed_type = "insufficient_funds"
    elif "NETWORK" in raw_error or "TIMEOUT" in raw_error:
        failed_type = "network_error"

    state: RecoveryAgentState = {
        "event_id": payload.get("id", f"evt_{uuid.uuid4().hex[:8]}"),
        "payment_id": pay_id,
        "subscription_id": sub_id,
        "currency": payment_entity.get("currency", "INR"),
        "amount_due": amount if amount > 0 else 1999.0,
        "failed_type": failed_type,
        "raw_error_code": raw_error,
        "current_retry_count": 1,
        "customer": {
            "customer_id": payment_entity.get("customer_id", "cust_live"),
            "email": payment_entity.get("email"),
            "phone": payment_entity.get("contact"),
            "plan_name": "Pro Tier",
            "arpu": amount if amount > 0 else 1999.0,
            "tenure_days": 90,
            "failure_count_30d": 0,
            "successful_payments": 3,
            "previous_recoveries": 0,
            "preferred_channel": "email" if payment_entity.get("email") else "whatsapp",
        },
        "action_history": [],
    }

    # Execute agent in background so Razorpay webhook acknowledges HTTP 200 immediately
    background_tasks.add_task(process_failed_payment, state)
    return {"status": "queued", "message": "Recovery agent dispatched"}
    
