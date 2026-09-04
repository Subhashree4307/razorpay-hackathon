Idea of the Problem Statement : 
An AI agent that, on every failed subscription charge, decides whether to act, what action to take, and how to talk to the customer, then executes a single best intervention (retry, rescue link, or personalized message) to maximize incremental recovered revenue.

It’s not just “smart retries”; it’s an autonomous decision‑making agent with a clear policy, tools, and memory.

How Agentic AI fits in (and what’s new vs. Razorpay)
Razorpay today gives you:
Fixed / semi‑smart retry schedules.
Webhooks (payment.failed, subscription.charged).
Payment Links API you can call manually or via scripts.

Your agent adds:
Per‑event decision making: “Do nothing vs. retry vs. send rescue link vs. escalate.”
Context‑aware messaging: LLM‑generated, personalized dunning copy based on failure reason, customer value, and history.
Explicit intervention policy: Only act when expected incremental value exceeds a threshold (aligned with your north‑star metric).
Judges will see a real “agent” that:
Observes events.

Thinks (scores, decides).

Acts (calls APIs, sends messages).

Learns (logs outcomes for future decisions).

Agent design (simple but convincing)
1. Trigger
Razorpay webhook: subscription.charged = failed (or payment.failed for recurring).

Your backend normalizes the event into a standard payload:

subscription_id, customer_id, amount, currency

error_code, error_description

attempt_number, plan_name, customer_email/phone

Basic history: past failures, last successful payment date (from your DB).

2. Agent “brain” (LLM + lightweight model)
You can implement this as a small orchestration service (FastAPI/Next.js + Python/Node) that calls an LLM (e.g., any provider you’re allowed to use in the hackathon).

Step A – Compute Recovery Propensity Score (0–100)
Use either:

A simple rule‑based scorer (fast, demo‑friendly), or

A tiny ML model (if you have time) trained on synthetic or historical data.

Features:

Failure type (soft vs. hard decline).

Attempt number (1st, 2nd, 3rd+).

Customer tenure (days since first successful payment).

ARPU / plan amount.

Past failure count in last 30/60 days.

Output:

recovery_score

baseline_recovery_prob (your estimate of natural recovery without intervention).

Step B – Agent Decision Prompt (LLM)
Pass structured context to the LLM, e.g.:

You are a Revenue Recovery Agent for a SaaS using Razorpay.
Input: failed subscription event with fields: {…}.
Recovery propensity score: 73.
Baseline recovery probability (no action): 0.45.
Possible actions:

DO_NOTHING

SCHEDULE_RETRY (with suggested delay in hours)

SEND_RESCUE_LINK (one‑click payment link)

SEND_PERSONALIZED_MESSAGE (email/WhatsApp with payment link)

ESCALATE_TO_SUPPORT

Task:

Estimate the incremental recovery probability for each action.

Estimate expected incremental revenue = (uplift × amount) − intervention_cost.

Choose the single best action if expected incremental revenue > threshold; otherwise choose DO_NOTHING.

If action involves messaging, draft a short, friendly message (max 3–4 sentences) using the provided customer and subscription details. Do not invent facts.

The LLM returns:

chosen_action

action_params (e.g., retry_delay_hours, channel, message_text)

reasoning (1–2 lines you can log/show in the dashboard for demo).

This is your agentic decision layer.

3. Agent “tools” (what it can execute)
Implement these as functions the agent can call:

Create Rescue Payment Link

Call Razorpay Payment Links API with:

amount, currency

subscription_id, failed_payment_id in metadata.

Return short_url.

Send Message

Email (SendGrid/Mailgun) or WhatsApp/Twilio.

Use the LLM‑drafted message, inject the rescue link.

Log message_id, channel, sent_at.

Schedule Retry

If you’re using Razorpay Subscriptions, you may not directly control retry timing, but you can:

Decide whether to let Razorpay’s built‑in retry run, or

Trigger a new charge attempt via your own logic (if your architecture allows).

For the hackathon, you can simulate this by:

Storing retry_scheduled_at and showing it in the dashboard.

Escalate to Support

Create a ticket (e.g., in a simple DB table or a Slack message) with:

Customer info, failure details, recovery score, agent reasoning.

All actions are logged with:

event_id, subscription_id, action_taken, agent_reasoning, timestamp.

4. Memory & Learning (lightweight but visible)
Store each decision + outcome:

When a rescue link is sent, listen to Razorpay webhooks:

payment.captured / payment.failed for that link.

subscription.activated / subscription.cancelled.

Update the record:

outcome: recovered, lost, still_pending.

time_to_recovery, action_that_worked.

In the dashboard, show:

Recovery rate by chosen action (SEND_RESCUE_LINK, SCHEDULE_RETRY, etc.).

Average recovery score for recovered vs. lost cases.

A simple chart: “Incremental recovery rate with agent vs. baseline (no‑agent simulation).”

This demonstrates the continuous observation and learning loop from your problem statement.

Minimal dashboard (for demo impact)
A single page with:

Top metrics:

Total failed subscription amount (last 7 days).

Estimated recoverable amount (sum(amount × recovery_score/100)).

Recovered via agent (INR and count).

Recent decisions table:

Customer (masked email/phone).

Amount, plan, failure reason.

Recovery score.

Action taken (DO_NOTHING, SEND_RESCUE_LINK, etc.).

Outcome (pending, recovered, lost).

“View reasoning” (show LLM’s 1–2 line explanation).

This makes the agent’s behavior transparent and judge‑friendly.

3‑day build plan (with Agentic AI)
Day 1

Set up:

Razorpay test account, webhooks endpoint.

DB schema (events, decisions, outcomes).

Implement:

Webhook ingestion + normalization.

Basic recovery propensity scorer (rule‑based).

LLM decision prompt + parser (JSON output).

Day 2

Implement agent tools:

Create Payment Link (Razorpay API).

Send email/WhatsApp with LLM‑drafted message.

Logging of decisions and actions.

Build basic dashboard (list events, scores, actions, outcomes).

Day 3

Wire in outcome tracking:

Handle payment.captured / payment.failed for rescue links.

Update decision records with outcomes.

Add simple analytics:

Recovery rate by action.

“Incremental recovered revenue” metric.

Polish:

Demo flow: trigger a test failure → show agent decision → send message/link → complete payment → show dashboard update.

Prepare a short narrative tying it to your north‑star metric.

Why this is a strong, Agentic AI hackathon project
It’s clearly agentic:

Perceives events (webhooks).

Reasons (score + LLM decision).

Acts (calls Razorpay + comms APIs).

Learns (logs outcomes, shows analytics).

It’s aligned with your problem statement:

Estimates natural recovery vs. intervention impact.

Chooses the highest‑value intervention.

Stops intervening when uplift is low (DO_NOTHING decisions).

It’s feasible in 3 days:

Core logic is small; complexity is in orchestration, not heavy ML.

You can fake some “learning” with rule‑based scoring and still call it an agent.

If you want, I can next give you:

A concrete DB schema (tables + fields).

A sample LLM prompt template (with exact JSON shape to parse).

A minimal API design (endpoints + request/response examples) to implement this quickly.

