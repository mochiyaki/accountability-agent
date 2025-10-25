# Market Design Discussion

## Overview
This document captures the design discussion for the multi-agent prediction market system that prices goal contracts dynamically.

---

## Core Concept Evolution

### Initial Problem
- Contracts had static base prices calculated once via LLM
- No mechanism for price updates when user submits progress updates
- Market was frozen after creation

### Solution: Dynamic Auction System
When a user submits an update (or creates a goal), trigger an **auction debate** where agents re-evaluate the contract price through discussion and trading.

---

## System Flow

### What Triggers a Market Event?
1. **Goal Creation** - treated as initial information/first "update"
2. **User Update Submission** - new progress information
3. System runs same flow for both: debate → spread generation → trade matching → settlement

### Market Cycle (per event)

```
Information Arrives (goal creation OR user update)
    ↓
DEBATE ROUNDS (group chat style)
    ├─ Round 1: All agents post independent theses
    ├─ Round 2: All agents respond to each other
    ├─ Round 3+: Optional additional rounds
    └─ All agents see full history
    ↓
SPREAD GENERATION (parallel)
    └─ Each agent independently analyzes full debate
    └─ Posts buy/sell prices
    ↓
ORDER MATCHING
    ├─ Sort buy orders: highest → lowest
    ├─ Sort sell orders: lowest → highest
    └─ Execute trades where overlap
    ↓
SETTLEMENT
    ├─ Update agent cash balances
    ├─ Update token holdings
    └─ Record trades
    ↓
Market Price Discovered (from executed trades)
```

---

## Debate System (Group Chat)

### Architecture
- **Per-event debate thread**: `debate:{goal_id}:{update_id}` in Redis
- Stores all agent messages chronologically
- Message format: agent_id, round_number, content, timestamp

### Turn-Based Rounds
1. **Round 1**: Agents independently evaluate (goal context + update history + current price if repricing)
2. **Round 2**: Agents see Round 1 theses, post counterarguments/analysis
3. **Optional Round 3+**: Convergence or final thoughts
4. **Spread Generation**: Each agent independently calculates buy/sell from full debate history

### Why Group Chat?
- Agents challenge each other's assumptions
- Prices converge through discussion
- Better price discovery than parallel thinking
- More realistic market dynamics

---

## Order Matching Logic

### Buy/Sell Terminology
- **Buy Price**: How much an agent will pay to buy 1 token
- **Sell Price**: How much an agent wants to receive to sell 1 token

### Matching Algorithm
```python
# Pseudocode
buy_orders = sorted([agent.buy_price for agent in agents], reverse=True)  # highest first
sell_orders = sorted([agent.sell_price for agent in agents])  # lowest first

trades = []
while buy_orders[0] >= sell_orders[0]:
    buyer = agent with buy_orders[0]
    seller = agent with sell_orders[0]
    trade_price = sell_orders[0]  # seller's price

    execute_trade(buyer, seller, trade_price, 1_token)

    buy_orders.remove(buyer.buy_price)
    sell_orders.remove(seller.sell_price)
```

### Why This Order?
- **Highest buyers first**: Most bullish agents (highest confidence) match first
- **Lowest sellers first**: Most bearish agents (lowest confidence) match first
- **Overlap = willingness to transact**: When highest buy ≥ lowest sell, there's agreement

### Trade Price
- Executed at **sell price** (the "asking" side)
- Simpler than mid-point
- Seller's posted price is the match point

---

## Agent Modeling

### Agent State
```python
{
  id: int,
  name: str,
  cash_balance: float,  # starts at $1000 or configurable
  token_holdings: int,  # can be negative (short)?
  portfolio_history: [(goal_id, token_amount, avg_price), ...]
}
```

### Per Goal
- Agent either: holds tokens (long), owes tokens (short), or flat
- Cash changes with trades
- At goal resolution: settle positions

---

## Open Questions / Tensions

### Token Supply & Market Thickness

**Problem**: With only 1 token per goal and 3 agents, market is very thin
- Agent A buys 1 token → only 2 more trades possible before liquidity dries up
- Price discovery is limited

**Options**:

#### Option 1: Allow Shorting
- Agents can sell tokens they don't own (go negative)
- Settle at goal resolution
- Pros: Liquid market, both sides can bet (success vs failure)
- Cons: Settlement complexity, requires careful handling of negatives

#### Option 2: Multiple Tokens Per Goal
- Mint 10-100 tokens per goal instead of 1
- All tokens equivalent (both success bets)
- Pros: Thicker market, more trading
- Cons: Why would multiple agents buy the same goal? Less natural

#### Option 3: Success/Failure Contracts (Like PredictIt)
- Each goal creates 100 "YES" tokens + 100 "NO" tokens
- YES = goal succeeds, NO = goal fails
- Sum to $100 payout at resolution
- Agents can bet either side
- Pros: Very liquid, natural adversarial betting, real prediction market
- Cons: More complex, need to track both sides

#### Option 4: Fractional Tokens
- Trade in 0.1, 0.5 increments instead of whole units
- More granular, higher liquidity
- Cons: Float precision headaches

### Recommendation
**Option 3 (Success/Failure Contracts)** seems most realistic and solves the liquidity problem naturally:
- "I think this goal will succeed" → buy YES token
- "I think this goal will fail" → buy NO token
- Market has natural adversarial tension
- 100 tokens on each side gives enough liquidity for 3+ agents to trade
- Aligns with real prediction markets (PredictIt, Polymarket)

---

## Implementation Plan (TODO)

### Phase 1: Core Market Engine
- [ ] Generalized `conduct_auction()` function
- [ ] Agent debate loop
- [ ] Order matching engine
- [ ] Settlement logic
- [ ] Trade recording

### Phase 2: Integration
- [ ] Replace `estimate_contract_base_price()` background task with market auction
- [ ] Add market event on goal creation
- [ ] Add market event on goal update submission

### Phase 3: Data Models
- [ ] Update `Trade` model with buy/sell semantics
- [ ] Update `Agent` model with portfolio tracking
- [ ] Add `Debate` model for storing debate messages
- [ ] Decide: single token vs success/failure contracts

### Phase 4: Frontend Integration
- [ ] Display debate messages
- [ ] Show trade history
- [ ] Show agent portfolios
- [ ] Polling for market completion (like current base_price polling)

---

## Next Steps
1. Decide on token model (single vs success/failure)
2. Code generalized market engine
3. Test with local agents
4. Integrate with goal creation workflow

