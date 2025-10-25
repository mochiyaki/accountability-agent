# Accountability Agent API Endpoints

## Base URL
```
http://localhost:8000
```

## Overview

The Accountability Agent API manages goals, tracks progress through updates, and runs a multi-agent prediction market that prices goals dynamically through debate and trading.

---

## Goals Endpoints

### Create Goal
**POST** `/goals`

Creates a new goal and triggers an initial market auction where agents debate and trade contracts.

**Request Body:**
```json
{
  "goal": "Complete project proposal",
  "measurement": "Submit 10-page document",
  "date": "31/12/2025"
}
```

**Parameters:**
- `goal` (string, required): Description of the goal
- `measurement` (string, required): How success will be measured
- `date` (string, required): Target completion date in **DD/MM/YYYY** format

**Response:** 201 Created
```json
{
  "id": 1,
  "description": "Complete project proposal (Measurement: Submit 10-page document)",
  "target_date": "2025-12-31",
  "created_at": "2025-10-25T14:30:00.123456",
  "status": "active",
  "payout_amount": 100,
  "outcome": null,
  "base_price": null
}
```

**Notes:**
- Returns immediately (200 OK) while market auction runs in background
- `base_price` will be populated after agents debate and trade (poll GET /goals/{id})
- Triggers initial market auction (update_id=0) automatically

**Example:**
```bash
curl -X POST http://localhost:8000/goals \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Learn Rust programming",
    "measurement": "Complete 10 chapters of book",
    "date": "31/12/2025"
  }'
```

---

### List All Goals
**GET** `/goals`

Retrieves all active goals, sorted by ID.

**Response:** 200 OK
```json
[
  {
    "id": 1,
    "description": "Learn Rust programming (Measurement: Complete 10 chapters of book)",
    "target_date": "2025-12-31",
    "created_at": "2025-10-25T14:30:00.123456",
    "status": "active",
    "payout_amount": 100,
    "outcome": null,
    "base_price": 55.25
  },
  {
    "id": 2,
    "description": "Run a 10K in an hour (Measurement: Speed of run)",
    "target_date": "2025-12-31",
    "created_at": "2025-10-25T14:31:00.123456",
    "status": "active",
    "payout_amount": 100,
    "outcome": null,
    "base_price": 62.50
  }
]
```

**Example:**
```bash
curl http://localhost:8000/goals
```

---

### Get Goal Details
**GET** `/goals/{goal_id}`

Retrieves a specific goal with current market price.

**Path Parameters:**
- `goal_id` (integer, required): ID of the goal

**Response:** 200 OK
```json
{
  "id": 1,
  "description": "Learn Rust programming (Measurement: Complete 10 chapters of book)",
  "target_date": "2025-12-31",
  "created_at": "2025-10-25T14:30:00.123456",
  "status": "active",
  "payout_amount": 100,
  "outcome": null,
  "base_price": 55.25
}
```

**Status Codes:**
- 200 OK: Goal found
- 404 Not Found: Goal doesn't exist

**Notes:**
- `base_price` is the market-discovered price (average of all executed trades)
- Initially null after goal creation, gets populated after first market auction

**Example:**
```bash
curl http://localhost:8000/goals/1
```

---

## Updates Endpoints

### Submit Goal Update
**POST** `/goals/{goal_id}/updates`

Submits progress update for a goal and triggers market re-evaluation. Agents debate the update and potentially trade based on new information.

**Path Parameters:**
- `goal_id` (integer, required): ID of the goal

**Request Body:**
```json
{
  "content": "Completed chapters 1-5, making good progress",
  "date": "2025-10-26"
}
```

**Parameters:**
- `content` (string, required): Description of the update
- `date` (string, required): Date of update in **YYYY-MM-DD** (ISO) format

**Response:** 201 Created
```json
{
  "id": 1,
  "goal_id": 1,
  "content": "Completed chapters 1-5, making good progress",
  "date": "2025-10-26",
  "created_at": "2025-10-26T10:15:00.123456"
}
```

**Status Codes:**
- 201 Created: Update submitted successfully
- 404 Not Found: Goal doesn't exist

**Notes:**
- Returns immediately while market auction runs in background
- Triggers market re-evaluation (auction with this update_id)
- Agents will see this update in debate context and may change their prices

**Example:**
```bash
curl -X POST http://localhost:8000/goals/1/updates \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Completed chapters 1-5, making good progress",
    "date": "2025-10-26"
  }'
```

---

### List Goal Updates
**GET** `/goals/{goal_id}/updates`

Retrieves all progress updates for a goal, sorted chronologically.

**Path Parameters:**
- `goal_id` (integer, required): ID of the goal

**Response:** 200 OK
```json
[
  {
    "id": 1,
    "goal_id": 1,
    "content": "Completed chapters 1-5",
    "date": "2025-10-26",
    "created_at": "2025-10-26T10:15:00.123456"
  },
  {
    "id": 2,
    "goal_id": 1,
    "content": "Completed chapters 6-8, on track",
    "date": "2025-10-27",
    "created_at": "2025-10-27T14:30:00.123456"
  }
]
```

**Status Codes:**
- 200 OK: Returns list (can be empty)
- 404 Not Found: Goal doesn't exist

**Example:**
```bash
curl http://localhost:8000/goals/1/updates
```

---

### Get Market Analysis for Update
**GET** `/goals/{goal_id}/updates/{update_id}/market-analysis`

Retrieves complete LLM thinking for a goal update: agent debate messages, price spreads, executed trades, and discovered market price.

**Path Parameters:**
- `goal_id` (integer, required): ID of the goal
- `update_id` (integer, required): ID of the update

**Response:** 200 OK
```json
{
  "update_id": 1,
  "update_content": "Completed chapters 1-5, making good progress",
  "update_date": "2025-10-26",
  "debate_messages": [
    {
      "agent_id": 1,
      "round_number": 1,
      "content": "Alice's independent analysis: Progress looks solid, 5 out of 10 chapters done suggests 50% completion. Risk factors include...",
      "timestamp": "2025-10-26T10:15:30.123456"
    },
    {
      "agent_id": 2,
      "round_number": 1,
      "content": "Bob's analysis: The update shows steady progress. With 8 weeks remaining and 50% done, achievability seems high...",
      "timestamp": "2025-10-26T10:15:40.123456"
    },
    {
      "agent_id": 1,
      "round_number": 2,
      "content": "Alice responds: I agree with Bob's timeline assessment. The consistent pace suggests high probability of success...",
      "timestamp": "2025-10-26T10:16:00.123456"
    }
  ],
  "agent_spreads": [
    {
      "agent_id": 1,
      "buy_price": 65.00,
      "sell_price": 75.00
    },
    {
      "agent_id": 2,
      "buy_price": 62.00,
      "sell_price": 72.00
    },
    {
      "agent_id": 3,
      "buy_price": 58.00,
      "sell_price": 70.00
    }
  ],
  "trades": [
    {
      "buyer_id": 2,
      "buyer_name": "Bob",
      "seller_id": 3,
      "seller_name": "Charlie",
      "price": 65.00,
      "quantity": 1,
      "timestamp": "2025-10-26T10:16:15.123456"
    },
    {
      "buyer_id": 1,
      "buyer_name": "Alice",
      "seller_id": 3,
      "seller_name": "Charlie",
      "price": 65.00,
      "quantity": 1,
      "timestamp": "2025-10-26T10:16:16.123456"
    }
  ],
  "market_price": 65.00
}
```

**Status Codes:**
- 200 OK: Market analysis found
- 404 Not Found: Goal or update doesn't exist

**Response Fields:**
- `debate_messages`: All debate rounds (2 rounds by default: independent analysis + responses)
- `agent_spreads`: Each agent's buy/sell prices after reviewing debate
- `trades`: Executed trades at clearing price
- `market_price`: Average price of executed trades

**Notes:**
- Shows **complete LLM reasoning** for frontend to display agent thinking
- Debate messages show how agents analyze the update
- Spreads show agent confidence levels (wider spread = less confident)
- Trades show market price discovery mechanism
- `market_price` is what gets stored in goal's `base_price`

**Example:**
```bash
curl http://localhost:8000/goals/1/updates/1/market-analysis
```

---

## Agents Endpoints

### Create Agent
**POST** `/agents`

Creates a new trading agent with initial cash balance.

**Request Body:**
```json
{
  "name": "Alice",
  "cash_balance": 1000.0
}
```

**Parameters:**
- `name` (string, required): Agent name
- `cash_balance` (float, optional): Starting cash for trading (default: 1000.0)

**Response:** 201 Created
```json
{
  "id": 1,
  "name": "Alice",
  "cash_balance": 1000.0,
  "token_holdings": {},
  "analyses": {},
  "created_at": "2025-10-25T14:30:00.123456"
}
```

**Notes:**
- Agents are auto-created if none exist (default: Alice, Bob, Charlie)
- `cash_balance`: Amount available for trading
- `token_holdings`: Map of goal_id → tokens owned (positive = long, negative = short)
- `analyses`: Map of goal_id → latest analysis summary (agent memory)

**Example:**
```bash
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Diana",
    "cash_balance": 1500.0
  }'
```

---

### List All Agents
**GET** `/agents`

Retrieves all agents with their current portfolios.

**Response:** 200 OK
```json
[
  {
    "id": 1,
    "name": "Alice",
    "cash_balance": 935.00,
    "token_holdings": {
      "1": 2,
      "2": -1
    },
    "analyses": {
      "1": "Steady progress, high confidence in success"
    },
    "created_at": "2025-10-25T14:30:00.123456"
  },
  {
    "id": 2,
    "name": "Bob",
    "cash_balance": 1065.00,
    "token_holdings": {
      "1": 1,
      "2": 0
    },
    "analyses": {
      "1": "Update shows good progress, probability increasing"
    },
    "created_at": "2025-10-25T14:30:05.123456"
  }
]
```

**Example:**
```bash
curl http://localhost:8000/agents
```

---

### Get Agent Details
**GET** `/agents/{agent_id}`

Retrieves details of a specific agent including portfolio and trading history.

**Path Parameters:**
- `agent_id` (integer, required): ID of the agent

**Response:** 200 OK
```json
{
  "id": 1,
  "name": "Alice",
  "cash_balance": 935.00,
  "token_holdings": {
    "1": 2,
    "2": -1
  },
  "analyses": {
    "1": "Steady progress, high confidence in success",
    "2": "Update shows deteriorating situation, low confidence"
  },
  "created_at": "2025-10-25T14:30:00.123456"
}
```

**Status Codes:**
- 200 OK: Agent found
- 404 Not Found: Agent doesn't exist

**Notes:**
- `cash_balance`: Remaining cash (decreases after buying, increases after selling)
- `token_holdings`: Position in each goal (key=goal_id, value=quantity)
  - Positive = bullish (owns tokens, profits if goal succeeds)
  - Negative = bearish (short position, profits if goal fails)
  - 0 = flat (no position)

**Example:**
```bash
curl http://localhost:8000/agents/1
```

---

## Common Workflows

### 1. Create Goal and Monitor Market
```bash
# 1. Create a goal
GOAL_ID=$(curl -X POST http://localhost:8000/goals \
  -H "Content-Type: application/json" \
  -d '{"goal": "Learn Rust", "measurement": "10 chapters", "date": "31/12/2025"}' \
  | jq '.id')

# 2. Wait for market auction (2-3 seconds)
sleep 2

# 3. Check if market price discovered
curl http://localhost:8000/goals/$GOAL_ID | jq '.base_price'

# 4. View market analysis for initial auction (update_id=0)
curl http://localhost:8000/goals/$GOAL_ID/updates/0/market-analysis | jq '.market_price'
```

### 2. Submit Update and See Price Change
```bash
# 1. Submit progress update
UPDATE=$(curl -X POST http://localhost:8000/goals/1/updates \
  -H "Content-Type: application/json" \
  -d '{"content": "Completed chapters 1-5", "date": "2025-10-26"}' \
  | jq '.id')

# 2. Wait for market re-evaluation
sleep 2

# 3. Check new market price
curl http://localhost:8000/goals/1 | jq '.base_price'

# 4. View agent debate and reasoning for this update
curl http://localhost:8000/goals/1/updates/$UPDATE/market-analysis | jq '.debate_messages'

# 5. See what prices agents posted
curl http://localhost:8000/goals/1/updates/$UPDATE/market-analysis | jq '.agent_spreads'

# 6. See executed trades
curl http://localhost:8000/goals/1/updates/$UPDATE/market-analysis | jq '.trades'
```

### 3. Track Agent Portfolios
```bash
# View all agent positions
curl http://localhost:8000/agents | jq '.[] | {name, cash_balance, token_holdings}'

# Track specific agent over time
curl http://localhost:8000/agents/1 | jq '{name, cash_balance, token_holdings, analyses}'
```

---

## Data Models

### Goal
```json
{
  "id": 1,
  "description": "Goal and measurement combined",
  "target_date": "2025-12-31",
  "created_at": "2025-10-25T14:30:00.123456",
  "status": "active",
  "payout_amount": 100,
  "outcome": null,
  "base_price": 55.25
}
```

### GoalUpdate
```json
{
  "id": 1,
  "goal_id": 1,
  "content": "Progress description",
  "date": "2025-10-26",
  "created_at": "2025-10-26T10:15:00.123456"
}
```

### Agent
```json
{
  "id": 1,
  "name": "Alice",
  "cash_balance": 1000.0,
  "token_holdings": { "1": 2, "2": -1 },
  "analyses": { "1": "Summary of analysis" },
  "created_at": "2025-10-25T14:30:00.123456"
}
```

### DebateMessage
```json
{
  "agent_id": 1,
  "round_number": 1,
  "content": "Agent's reasoning about the goal...",
  "timestamp": "2025-10-26T10:15:30.123456"
}
```

### AgentSpread
```json
{
  "agent_id": 1,
  "buy_price": 65.00,
  "sell_price": 75.00
}
```

### MarketAnalysis
```json
{
  "update_id": 1,
  "update_content": "Update description",
  "update_date": "2025-10-26",
  "debate_messages": [...],
  "agent_spreads": [...],
  "trades": [...],
  "market_price": 65.00
}
```

---

## Error Handling

All endpoints return standard HTTP status codes and error messages:

**404 Not Found:**
```json
{
  "detail": "Goal not found"
}
```

**400 Bad Request:**
```json
{
  "detail": "Date must be in DD/MM/YYYY format"
}
```

---

## Rate Limiting & Performance

- **Market auctions** run asynchronously (non-blocking)
- **LLM calls** may take 5-10 seconds per debate round
- **Debate rounds**: 2 rounds by default (1 independent + 1 responsive)
- **3 agents** by default (Alice, Bob, Charlie)
- Poll endpoints with 1-2 second delays for market completion

---

## API Docs

For interactive exploration, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

**Last Updated:** 2025-10-25
**Version:** 1.0.0
