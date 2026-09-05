# Recovery Agent

An autonomous revenue-recovery system for failed Razorpay subscription payments.

Recovery Agent receives a failed-payment event, scores the customer and failure context, asks a Groq-powered decision agent to choose the best intervention, executes that intervention, and stores the decision for merchant review.

The project includes:

- A FastAPI and LangGraph backend
- A deterministic recovery scoring and payoff engine
- Groq structured decision-making with `openai/gpt-oss-20b`
- Razorpay test payment-link generation
- Retry scheduling and support escalation tools
- MongoDB persistence for recovery events
- A light Razorpay-inspired merchant dashboard
- A `payment.captured` webhook that changes a pending intervention into a confirmed recovery

> This repository is configured for Razorpay test-mode demonstrations. The simulation endpoint creates representative failure events without charging a real customer.

## Problem

Subscription payment failures do not all need the same response. Retrying an expired card wastes attempts, while messaging a customer during a temporary gateway outage creates unnecessary friction. High-value accounts may need human support, and fraud signals should stop automated recovery.

The agent answers three questions for every failed payment:

1. Should the merchant act at all?
2. Which single action has the best expected incremental revenue?
3. Why was that action selected?

Supported actions:

- `DO_NOTHING`
- `SCHEDULE_RETRY`
- `SEND_RESCUE_LINK`
- `SEND_PERSONALIZED_MESSAGE`
- `ESCALATE_TO_SUPPORT`

## Solution

The system combines deterministic economics with LLM reasoning:

1. Normalize the failed payment and customer context.
2. Calculate a recovery propensity score from failure type, attempt number, tenure, payment history, failure history, and amount.
3. Estimate baseline recovery probability without intervention.
4. Calculate expected incremental revenue for every possible action:

   `expected incremental revenue = (action recovery probability - baseline probability) * amount - intervention cost`

5. Send the ranked payoff matrix and business policy to Groq.
6. Validate the structured decision.
7. Execute one action through the appropriate tool.
8. Store the decision, reasoning, action history, and outcome in MongoDB.
9. Mark the event as `RECOVERED` only after a `payment.captured` webhook is received.

## Project Structure

```text
.
├── backend/
│   └── app/
│       ├── main.py                 # FastAPI routes and webhook handlers
│       ├── schema.py               # Simulation request model
│       ├── test_graph.py           # Direct agent smoke-test scenarios
│       └── agent/
│           ├── decision.py          # Groq structured decision node
│           ├── execution.py         # Rescue link, retry, and escalation tools
│           ├── graph.py              # LangGraph orchestration
│           ├── score.py              # Scoring and payoff calculations
│           └── state.py              # Agent state and action types
├── frontend/
│   ├── src/App.tsx                 # Landing page and dashboard behavior
│   ├── src/App.css                 # Razorpay-inspired light UI
│   └── package.json
├── .env                            # Local secrets; never commit this file
├── pyproject.toml                  # Python dependencies
└── README.md
```

## Requirements

- Python 3.12 or newer
- Node.js and npm
- A MongoDB Atlas database or local MongoDB instance
- A Groq API key
- Razorpay test credentials for live payment-link API behavior

## Environment Variables

Create a `.env` file in the repository root:

```env
GROQ_API_KEY=your_groq_api_key
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
DATABASE_NAME=razorpay_hackathon
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_razorpay_test_secret
```

Keep `.env` private. Do not commit API keys, database passwords, or Razorpay secrets.

For MongoDB Atlas, add the machine's public IP address under **Security -> Network Access**.

## Installation

### Backend

From the repository root:

```powershell
uv sync
```

If the virtual environment already exists and dependencies need to be refreshed:

```powershell
uv pip install --python .venv\Scripts\python.exe -e .
```

### Frontend

```powershell
cd frontend
npm install
```

## Run the Project

Use two terminals.

### Terminal 1: Backend

Run this from the repository root:

```powershell
$env:PYTHONPATH="$PWD;$PWD\backend"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Backend URLs:

- Health: http://127.0.0.1:8000/api/health
- Swagger API docs: http://127.0.0.1:8000/docs
- Recovery records: http://127.0.0.1:8000/api/recoveries

### Terminal 2: Frontend

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open the dashboard at:

http://127.0.0.1:5173/

## Dashboard Demo Flow

1. Open the landing page and select **Open command center**.
2. In **Live payments**, choose a scenario such as expired card, network error, insufficient funds, or fraud.
3. Select **Agent to action**.
4. The request is sent to `POST /api/test/simulate-failure`.
5. The agent scores the event, calls Groq, selects one action, and returns reasoning.
6. Open **Execution** to inspect the action, score, reasoning, rescue link, or retry schedule.
7. Open **History** to view MongoDB-persisted events.
8. Use a `payment.captured` webhook to confirm a recovery and update the KPIs.

The dashboard exposes eight demonstration scenarios based on the policy engine:

- Expired card -> payment-link or personalized-message intervention
- Network error -> scheduled retry
- Card declined -> rescue, message, or escalation based on context
- Insufficient funds -> delayed retry or empathetic message
- Incorrect CVC -> payment-link intervention
- Timeout -> scheduled retry
- Processing error -> scheduled retry
- Fraudulent payment -> `DO_NOTHING`

## API Reference

### Health

```http
GET /api/health
```

### Simulate a Failed Payment

```http
POST /api/test/simulate-failure
Content-Type: application/json
```

Example body:

```json
{
  "plan_name": "Pro Monthly",
  "amount_due": 4999,
  "failed_type": "expired_card",
  "raw_error_code": "EXPIRED_CARD",
  "current_retry_count": 1,
  "customer_name": "Arjun Mehta",
  "customer_email": "arjun@example.com",
  "customer_phone": "+919876543210",
  "preferred_channel": "whatsapp",
  "tenure_days": 120,
  "successful_payments": 4
}
```

### List Recovery Records

```http
GET /api/recoveries?limit=50&skip=0
```

### Razorpay Webhook

```http
POST /api/webhook/razorpay
```

The webhook handles:

- `payment.failed`
- `subscription.charged`
- `payment.captured`

A `payment.captured` event updates matching records with:

```json
{
  "status": "RECOVERED",
  "recovered_amount": 4999,
  "recovered_at": "2026-09-05T12:00:00+00:00"
}
```

## Testing

### Agent Graph Smoke Test

From the repository root:

```powershell
.\.venv\Scripts\python.exe backend\app\test_graph.py
```

This runs expired-card, network-error, and enterprise-risk scenarios and prints the score, baseline probability, recommendation, chosen action, reasoning, and action history.

### Backend Syntax Check

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend\app
```

### Frontend Production Build

```powershell
cd frontend
npm run build
```

## Adding Dashboard Screenshots

Store screenshots in a new folder:

```text
docs/screenshots/
├── landing.png
├── live-payments.png
├── execution.png
├── history.png
└── recovered-kpis.png
```


```md
## Dashboard Screenshots

### Landing Page
![Recovery Agent landing page](docs/screenshots/landing.png)

### Live Payments
![Live payment scenarios](docs/screenshots/live-payments.png)

### Agent Execution
![Agent execution with reasoning](docs/screenshots/execution.png)

### Recovery History
![Recovery history](docs/screenshots/history.png)

### Confirmed Recovery KPIs
![Confirmed recovered payment KPIs](docs/screenshots/recovered-kpis.png)
```

The image path is relative to `README.md`, so the files must exist under `docs/screenshots/` in the repository.


## Design Decisions

- **Deterministic scoring:** keeps the economic calculations transparent and repeatable.
- **Groq structured output:** adds contextual reasoning and personalized message generation.
- **LangGraph:** makes the observe -> score -> decide -> act flow explicit.
- **MongoDB:** stores decisions, action history, and outcomes for merchant visibility.
- **Test-mode payment links:** demonstrate execution without charging real customers.
- **Light merchant dashboard:** keeps the interface focused on scanning, action, and auditability.

## Future Improvements

- Verify Razorpay webhook signatures before processing events.
- Add idempotency handling for duplicate webhook deliveries.
- Add background jobs for long-running actions.
- Add authentication and merchant-level data isolation.
- Add charts for recovery rate by action and incremental revenue versus baseline.
- Add real email, WhatsApp, and support-ticket provider integrations.
- Add an outcome feedback loop to recalibrate affinity and recovery probabilities.

## License

This project was created for a Razorpay hackathon demonstration.
