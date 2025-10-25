import json
import redis
import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator, AfterValidator
from typing import List, Optional, Annotated
from datetime import datetime, date

def validate_iso_date(v: str) -> str:
    """Validate that a string is a valid ISO format date (YYYY-MM-DD)"""
    try:
        datetime.fromisoformat(v).date()
        return v
    except (ValueError, TypeError):
        raise ValueError("Date must be in ISO format (YYYY-MM-DD)")

ISODate = Annotated[str, AfterValidator(validate_iso_date)]

# Load environment variables
load_dotenv()

app = FastAPI(title="Accountability Agent API", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST'),
    port=int(os.getenv('REDIS_PORT')),
    username=os.getenv('REDIS_USERNAME'),
    password=os.getenv('REDIS_PASSWORD'),
    decode_responses=True
)

# Data models
class Goal(BaseModel):
    id: Optional[int] = None
    description: str
    target_date: ISODate
    created_at: Optional[str] = None
    status: Optional[str] = "active"  # active, resolved
    payout_amount: int = 100
    outcome: Optional[str] = None  # success, failure, null if unresolved
    base_price: Optional[float] = None

class DailyTask(BaseModel):
    id: Optional[int] = None
    goal_id: int
    description: str
    assigned_date: ISODate
    completed: bool = False
    created_at: Optional[str] = None

class Agent(BaseModel):
    id: Optional[int] = None
    name: str
    cash_balance: float = 1000.0  # Starting cash for trading
    token_holdings: dict = {}  # goal_id -> token_amount (can be negative for shorts)
    analyses: dict = {}  # goal_id -> latest analysis summary (what they think about the goal)
    created_at: Optional[str] = None

class Trade(BaseModel):
    id: Optional[int] = None
    goal_id: int
    buyer_agent_id: int
    seller_agent_id: int
    price_per_token: float
    tokens_exchanged: float
    created_at: Optional[str] = None

class DebateMessage(BaseModel):
    agent_id: int
    round_number: int
    content: str
    timestamp: str

class AgentSpread(BaseModel):
    agent_id: int
    buy_price: float  # How much they'll pay per token
    sell_price: float  # How much they want to receive per token

class GoalUpdate(BaseModel):
    id: Optional[int] = None
    goal_id: int
    content: str
    date: ISODate
    created_at: Optional[str] = None

class MarketAnalysis(BaseModel):
    """Complete LLM thinking for a goal update"""
    update_id: int
    update_content: str
    update_date: str
    debate_messages: List[DebateMessage]
    agent_spreads: List[AgentSpread]
    trades: List[dict]  # List of executed trades
    market_price: Optional[float] = None

class CreateGoalRequest(BaseModel):
    goal: str
    measurement: str
    date: str  # DD/MM/YYYY format

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate that date is in DD/MM/YYYY format"""
        try:
            datetime.strptime(v, "%d/%m/%Y")
            return v
        except ValueError:
            raise ValueError("Date must be in DD/MM/YYYY format")

class CreateGoalUpdateRequest(BaseModel):
    content: str
    date: ISODate

class CreateAgentRequest(BaseModel):
    name: str
    cash_balance: float = 1000.0

class ResolveGoalRequest(BaseModel):
    outcome: str  # "success" or "failure"

# Helper functions for Redis operations
def get_next_id(key: str) -> int:
    """Get next ID for a resource"""
    return int(redis_client.incr(key))

def serialize_datetime() -> str:
    """Get current datetime as ISO format string"""
    return datetime.now().isoformat()

def get_goal(goal_id: int) -> Optional[Goal]:
    """Fetch goal from Redis"""
    data = redis_client.get(f"goal:{goal_id}")
    if not data:
        return None
    return Goal(**json.loads(data))

def get_agent(agent_id: int) -> Optional[Agent]:
    """Fetch agent from Redis"""
    data = redis_client.get(f"agent:{agent_id}")
    if not data:
        return None
    return Agent(**json.loads(data))

def save_agent(agent: Agent):
    """Save agent to Redis"""
    redis_client.set(f"agent:{agent.id}", json.dumps(agent.model_dump()))
    redis_client.sadd("agents:all", agent.id)

def get_all_agents() -> List[Agent]:
    """Fetch all agents from Redis"""
    agent_ids = list(redis_client.smembers("agents:all") or [])  # type: ignore
    if not agent_ids:
        return []

    agents = []
    for agent_id in agent_ids:
        agent = get_agent(int(agent_id))
        if agent:
            agents.append(agent)

    return sorted(agents, key=lambda a: a.id)

def save_goal(goal: Goal):
    """Save goal to Redis"""
    goal_data = json.dumps(goal.model_dump())
    redis_client.set(f"goal:{goal.id}", goal_data)
    redis_client.sadd("goals:all", goal.id)
    print(f"Saved goal {goal.id} to Redis: {goal_data}", flush=True)

def get_goal_update(update_id: int) -> Optional[GoalUpdate]:
    """Fetch goal update from Redis"""
    data = redis_client.get(f"update:{update_id}")
    if not data:
        return None
    return GoalUpdate(**json.loads(data))

def save_goal_update(update: GoalUpdate):
    """Save goal update to Redis"""
    redis_client.set(f"update:{update.id}", json.dumps(update.model_dump()))
    redis_client.sadd(f"goal:{update.goal_id}:updates", update.id)

def get_goal_updates(goal_id: int) -> List[GoalUpdate]:
    """Fetch all updates for a goal"""
    update_ids = list(redis_client.smembers(f"goal:{goal_id}:updates") or [])  # type: ignore
    if not update_ids:
        return []

    updates = []
    for update_id in update_ids:
        update = get_goal_update(int(update_id))
        if update:
            updates.append(update)

    return sorted(updates, key=lambda u: u.created_at or "", reverse=True)

# Market System Helper Functions

def store_debate_message(goal_id: int, update_id: int, agent_id: int, round_number: int, content: str):
    """Store a debate message in Redis"""
    message = {
        "agent_id": agent_id,
        "round_number": round_number,
        "content": content,
        "timestamp": serialize_datetime(),
    }
    # Store as list of messages per debate
    key = f"debate:{goal_id}:{update_id}"
    redis_client.rpush(key, json.dumps(message))

def get_debate_messages(goal_id: int, update_id: int) -> List[DebateMessage]:
    """Fetch all debate messages for a goal/update"""
    key = f"debate:{goal_id}:{update_id}"
    messages_raw = redis_client.lrange(key, 0, -1)
    if not messages_raw:
        return []
    return [DebateMessage(**json.loads(msg)) for msg in messages_raw]

def get_debate_by_round(goal_id: int, update_id: int, round_number: int) -> List[DebateMessage]:
    """Get all messages from a specific debate round"""
    all_messages = get_debate_messages(goal_id, update_id)
    return [msg for msg in all_messages if msg.round_number == round_number]

def store_agent_spreads(goal_id: int, update_id: int, spreads: List[AgentSpread]):
    """Store agent spreads to Redis for a goal update"""
    spreads_data = [spread.model_dump() for spread in spreads]
    redis_client.set(f"spreads:{goal_id}:{update_id}", json.dumps(spreads_data))
    print(f"Stored {len(spreads)} spreads for goal:{goal_id}:update:{update_id}", flush=True)

def get_agent_spreads_from_redis(goal_id: int, update_id: int) -> List[AgentSpread]:
    """Retrieve stored agent spreads from Redis"""
    data = redis_client.get(f"spreads:{goal_id}:{update_id}")
    if not data:
        return []
    spreads_data = json.loads(data)
    return [AgentSpread(**spread) for spread in spreads_data]

def save_agent_history_entry(agent_id: int, goal_id: int, update_id: int, spread: AgentSpread, market_price: Optional[float]):
    """Save agent's prediction to their history for future reference"""
    history_entry = {
        "goal_id": goal_id,
        "update_id": update_id,
        "buy_price": spread.buy_price,
        "sell_price": spread.sell_price,
        "market_price": market_price,
        "timestamp": serialize_datetime()
    }
    key = f"agent:{agent_id}:history"
    redis_client.rpush(key, json.dumps(history_entry))
    market_formatted = f"${market_price:.2f}" if market_price else "N/A"
    print(f"  Saved history for Agent {agent_id}: Goal #{goal_id}, predicted ${spread.buy_price:.2f}, market was {market_formatted}", flush=True)

def get_agent_history(agent_id: int, limit: int = 5) -> List[dict]:
    """Retrieve agent's last N history entries"""
    key = f"agent:{agent_id}:history"
    history_raw = redis_client.lrange(key, -limit, -1)  # Get last 'limit' entries
    if not history_raw:
        return []
    return [json.loads(entry) for entry in history_raw]

def get_trades_for_update(goal_id: int, update_id: int) -> List[Trade]:
    """Retrieve trades executed for a specific goal update"""
    trade_ids = list(redis_client.smembers(f"goal:{goal_id}:update:{update_id}:trades") or [])  # type: ignore
    trades = []
    for trade_id in trade_ids:
        data = redis_client.get(f"trade:{int(trade_id)}")
        if data:
            trade = Trade(**json.loads(data))
            trades.append(trade)
    return sorted(trades, key=lambda t: t.id)

def initialize_goal_tokens(goal_id: int, token_supply: int = 100):
    """Initialize token supply for a goal (100 tokens, all unowned initially)"""
    redis_client.set(f"goal:{goal_id}:token_supply", token_supply)

def match_orders(spreads: List[AgentSpread]) -> List[tuple]:
    """
    Match buy and sell orders from agent spreads.
    Returns list of (buyer_agent_id, seller_agent_id, price, quantity) tuples.

    Algorithm:
    - Sort buy prices: highest first (most bullish)
    - Sort sell prices: lowest first (most bearish)
    - Match where highest_buy >= lowest_sell at sell_price
    """
    if not spreads:
        return []

    # Sort buy orders (descending) and sell orders (ascending)
    buy_orders = sorted(spreads, key=lambda s: s.buy_price, reverse=True)
    sell_orders = sorted(spreads, key=lambda s: s.sell_price)

    trades = []
    buy_idx = 0
    sell_idx = 0

    while buy_idx < len(buy_orders) and sell_idx < len(sell_orders):
        buyer = buy_orders[buy_idx]
        seller = sell_orders[sell_idx]

        # Check if there's overlap (willing to transact)
        if buyer.buy_price >= seller.sell_price:
            # Trade happens at sell price
            trade = (buyer.agent_id, seller.agent_id, seller.sell_price, 1.0)
            trades.append(trade)
            buy_idx += 1
            sell_idx += 1
        else:
            # No more matches possible
            break

    return trades

def auction_fallback(spreads: List[AgentSpread]) -> List[tuple]:
    """
    Fallback auction when order book doesn't converge (for initial market seeding).
    Uses clearing price algorithm: find price that maximizes trade volume.

    Algorithm:
    - For each possible price point between min sell and max buy
    - Count how many buyers and sellers would trade at that price
    - Pick the price that clears the most volume
    - Execute all trades at that clearing price
    """
    if len(spreads) < 2:
        return []

    buy_prices = [s.buy_price for s in spreads]
    sell_prices = [s.sell_price for s in spreads]

    highest_buy = max(buy_prices)
    lowest_sell = min(sell_prices)

    # If spreads overlap, regular matching should have worked
    if highest_buy >= lowest_sell:
        return []

    print(f"  Spreads don't converge: highest_buy=${highest_buy:.2f} < lowest_sell=${lowest_sell:.2f}", flush=True)
    print(f"  Running auction fallback to discover clearing price...", flush=True)

    # Try prices from lowest_sell down to highest_buy in 5 cent increments
    best_price = None
    best_volume = 0

    price = lowest_sell
    while price >= highest_buy - 0.01:  # Small buffer
        # Count buyers willing to buy at this price and sellers willing to sell
        buyers_at_price = [s for s in spreads if s.buy_price >= price]
        sellers_at_price = [s for s in spreads if s.sell_price <= price]

        # Volume is min of buyers and sellers (pairing constraint)
        volume = min(len(buyers_at_price), len(sellers_at_price))

        if volume > best_volume:
            best_volume = volume
            best_price = price

        price -= 0.05

    if best_price is None or best_volume == 0:
        print(f"  Could not find clearing price", flush=True)
        return []

    print(f"  Clearing price discovered: ${best_price:.2f} (volume: {best_volume} tokens)", flush=True)

    # Execute trades at clearing price
    buyers = sorted([s for s in spreads if s.buy_price >= best_price],
                   key=lambda s: s.buy_price, reverse=True)
    sellers = sorted([s for s in spreads if s.sell_price <= best_price],
                    key=lambda s: s.sell_price)

    trades = []
    for i in range(min(len(buyers), len(sellers))):
        trade = (buyers[i].agent_id, sellers[i].agent_id, best_price, 1.0)
        trades.append(trade)
        print(f"    Agent {buyers[i].agent_id} buys from Agent {sellers[i].agent_id} @ ${best_price:.2f}", flush=True)

    return trades

def settle_trades(goal_id: int, trades: List[tuple], update_id: int = 0):
    """
    Settle trades by updating agent cash and token holdings in Redis.
    trades: list of (buyer_agent_id, seller_agent_id, price_per_token, quantity)
    update_id: Market event ID (0 for initial auction, >0 for updates)
    """
    for buyer_id, seller_id, price, qty in trades:
        buyer = get_agent(buyer_id)
        seller = get_agent(seller_id)

        if not buyer or not seller:
            continue

        # Calculate trade amount
        trade_amount = price * qty

        # Update cash balances
        buyer.cash_balance -= trade_amount
        seller.cash_balance += trade_amount

        # Update token holdings
        goal_id_str = str(goal_id)
        buyer.token_holdings[goal_id_str] = buyer.token_holdings.get(goal_id_str, 0) + qty
        seller.token_holdings[goal_id_str] = seller.token_holdings.get(goal_id_str, 0) - qty

        # Save updated agents to Redis
        save_agent(buyer)
        save_agent(seller)

        print(f"  Trade Settled:")
        print(f"    Buyer: {buyer.name} (ID {buyer_id})")
        print(f"      Cash: ${buyer.cash_balance:.2f}")
        print(f"      Tokens for Goal #{goal_id}: {buyer.token_holdings.get(goal_id_str, 0)}")
        print(f"    Seller: {seller.name} (ID {seller_id})")
        print(f"      Cash: ${seller.cash_balance:.2f}")
        print(f"      Tokens for Goal #{goal_id}: {seller.token_holdings.get(goal_id_str, 0)}")
        print(f"    Amount: {qty} tokens @ ${price:.2f} = ${trade_amount:.2f}")

        # Record the trade in Redis
        trade_id = get_next_id("trade:id")
        trade = Trade(
            id=trade_id,
            goal_id=goal_id,
            buyer_agent_id=buyer_id,
            seller_agent_id=seller_id,
            price_per_token=price,
            tokens_exchanged=qty,
            created_at=serialize_datetime(),
        )
        redis_client.set(f"trade:{trade_id}", json.dumps(trade.model_dump()))
        redis_client.sadd(f"goal:{goal_id}:trades", trade_id)
        redis_client.sadd(f"goal:{goal_id}:update:{update_id}:trades", trade_id)
        print(f"    Trade recorded in Redis (ID: {trade_id})")

def send_openrouter(
    messages: List[dict],
    model: str = "moonshotai/kimi-k2-0905",
    provider: Optional[dict] = None,
) -> Optional[str]:
    """
    Send a request to OpenRouter API and return the message content.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model: Model to use (default: moonshotai/kimi-k2-0905)
        provider: Optional provider config dict with 'order' and 'allow_fallbacks'

    Returns:
        The message content from the API response, or None if request fails
    """
    try:
        print("\n" + "="*80, flush=True)
        print("OPENROUTER REQUEST", flush=True)
        print("="*80, flush=True)
        print(f"Model: {model}", flush=True)
        print(f"Provider: {provider}", flush=True)
        print(f"Number of messages: {len(messages)}", flush=True)

        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Accountability Agent",
            "Content-Type": "application/json",
        }

        print("\nHeaders:", flush=True)
        for key, value in headers.items():
            if key == "Authorization":
                print(f"  {key}: Bearer [REDACTED]", flush=True)
            else:
                print(f"  {key}: {value}", flush=True)

        payload = {
            "model": model,
            "messages": messages,
        }

        if provider:
            payload["provider"] = provider

        print("\nPayload:", flush=True)
        print(f"  model: {payload['model']}", flush=True)
        if provider:
            print(f"  provider: {payload['provider']}", flush=True)
        print(f"  messages:", flush=True)
        for i, msg in enumerate(payload['messages']):
            print(f"    [{i}] role: {msg['role']}", flush=True)
            print(f"        content: {msg['content']}", flush=True)

        print("\nSending to: https://openrouter.ai/api/v1/chat/completions", flush=True)

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )

        print(f"\nResponse Status: {response.status_code}", flush=True)
        response.raise_for_status()
        data = response.json()

        print("\nResponse Data:", flush=True)
        print(f"  Model: {data.get('model')}", flush=True)
        print(f"  Choices: {len(data.get('choices', []))}", flush=True)
        print(f"  Usage: {data.get('usage')}", flush=True)

        message_content = data["choices"][0]["message"]["content"]

        print(f"\nMessage Content:", flush=True)
        print(f"  {message_content}", flush=True)

        print("="*80 + "\n", flush=True)
        return message_content
    except Exception as e:
        print(f"\nError calling OpenRouter: {e}", flush=True)
        print("="*80 + "\n", flush=True)
        return None


def _call_llm_for_price(prompt: str) -> Optional[float]:
    """Make a single LLM call to estimate price. Returns the price or None if extraction fails."""
    provider_config = {
        "order": ["groq"],
        "allow_fallbacks": False,
    }

    message_content = send_openrouter(
        messages=[{"role": "user", "content": prompt}],
        provider=provider_config,
    )

    if message_content:
        match = re.search(r'<price>([\d.]+)</price>', message_content)
        if match:
            price = float(match.group(1))
            print(f"Estimated price: ${price}")
            return price

    return None

def _process_agent_analysis(agent_id: int, agent_name: str, goal_id: int, update_id: int, prompt: str) -> tuple[Optional[DebateMessage], Optional[AgentSpread]]:
    """Helper function to process a single agent's analysis and pricing."""
    response = send_openrouter([{"role": "user", "content": prompt}])

    if not response:
        return None, None

    # Extract and store the full debate message
    store_debate_message(goal_id, update_id, agent_id, 1, response)
    debate_msg = DebateMessage(
        agent_id=agent_id,
        round_number=1,
        content=response,
        timestamp=serialize_datetime()
    )

    # Extract the analysis part (everything before <buy> tag)
    analysis_match = re.search(r'^(.*?)(?=<buy>|$)', response, re.DOTALL)
    if analysis_match:
        analysis_text = analysis_match.group(1).strip()
        # Save agent's analysis for this goal
        agent = get_agent(agent_id)
        if agent:
            agent.analyses[str(goal_id)] = analysis_text
            save_agent(agent)

    # Extract bid/ask prices from the response
    buy_match = re.search(r'<buy>\$?([\d.]+)</buy>', response)
    sell_match = re.search(r'<sell>\$?([\d.]+)</sell>', response)

    spread = None
    is_auction = update_id == 0

    if buy_match:
        buy_price = float(buy_match.group(1))

        # Validate spreads based on agent's cash balance
        agent = get_agent(agent_id)
        if agent:
            # Agent can't bid more per token than their total cash (can't afford even 1 token)
            if buy_price > agent.cash_balance:
                print(f"  Warning: Agent {agent_id} buy_price (${buy_price:.2f}) exceeds cash (${agent.cash_balance:.2f}). Capping to ${agent.cash_balance:.2f}.", flush=True)
                buy_price = agent.cash_balance

        # In auction (update_id=0), only buy price is needed; in trading rounds, both are needed
        if is_auction:
            spread = AgentSpread(
                agent_id=agent_id,
                buy_price=buy_price,
                sell_price=0  # Not applicable in auction
            )
        elif sell_match:
            sell_price = float(sell_match.group(1))
            spread = AgentSpread(
                agent_id=agent_id,
                buy_price=buy_price,
                sell_price=sell_price
            )

    return debate_msg, spread

def conduct_debate_round(goal_id: int, update_id: int, agents: List[Agent]) -> tuple[List[DebateMessage], List[AgentSpread]]:
    """
    Conduct debate and pricing in a single round (concurrent).
    Each agent analyzes the goal and provides their bid/ask prices in one API call.
    All agents run in parallel.
    Returns: (debate_messages, spreads)
    """
    goal = get_goal(goal_id)
    updates = get_goal_updates(goal_id)

    if not goal:
        return [], []

    # Build context for agents
    goal_context = f"Goal #{goal_id}: {goal.description}\nTarget Date: {goal.target_date}"

    # Build update history (all updates, no truncation)
    updates_context = ""
    if updates:
        updates_context = "Goal Progress Updates:\n"
        for update in updates:  # All updates for complete context
            updates_context += f"- {update.date}: {update.content}\n"
        updates_context += "\n"

    # Get the relevant date: update date if this is an update, otherwise today
    if update_id == 0:
        current_date = datetime.now().date().isoformat()
    else:
        update = get_goal_update(update_id)
        current_date = update.date if update else datetime.now().date().isoformat()

    # Build prompts for all agents
    agent_prompts = []
    for agent in agents:
        # Calculate agent's net worth across all positions
        cash = agent.cash_balance
        total_liabilities = 0
        total_assets = 0
        long_positions = []
        short_positions = []

        for goal_id_str, tokens in agent.token_holdings.items():
            if tokens > 0:
                # Long position = asset (worth $100/token at 100% success)
                total_assets += tokens * 100
                long_positions.append(f"Goal #{goal_id_str}: +{int(tokens)} tokens (${tokens * 100:.2f})")
            elif tokens < 0:
                # Short position = liability (owes $100/token at 100% failure)
                liability = abs(tokens) * 100
                total_liabilities += liability
                short_positions.append(f"Goal #{goal_id_str}: {int(tokens)} tokens (-${liability:.2f})")

        net_worth = cash + total_assets - total_liabilities

        # Get agent's current token position for this goal
        token_position = agent.token_holdings.get(str(goal_id), 0)

        # Build position strings
        long_str = "\n  ".join(long_positions) if long_positions else "None"
        short_str = "\n  ".join(short_positions) if short_positions else "None"

        position_info = f"""PORTFOLIO:
- Cash: ${cash:.2f}
- Long Tokens (across all goals):
  {long_str}
  Total: ${total_assets:.2f}
- Short Token Liabilities (across all goals):
  {short_str}
  Total: -${total_liabilities:.2f}
- Net Worth: ${net_worth:.2f}

Current Position (this goal): {int(token_position)} tokens"""

        # Get agent's previous analysis on THIS GOAL if exists
        agent_prev_analysis = agent.analyses.get(str(goal_id), "")
        prev_analysis_context = f"Your previous analysis on this goal: {agent_prev_analysis}\n\n" if agent_prev_analysis else ""

        # Determine if this is an auction round or a trading round
        is_auction = update_id == 0
        goal = get_goal(goal_id)

        if is_auction:
            market_context = """AUCTION ROUND (Initial Price Discovery):
This is the first round. Submit your bid price to discover the market price.
The highest bids set the clearing price - no one is forced to sell."""
            task_description = """Your task: Provide an independent analysis of whether this goal will be achieved, then submit your bid price.

First, provide your analysis (2-3 sentences on probability of success, key risks, time remaining).

Then, submit your bid price for success tokens - the maximum you'd pay per token:
- Buy price: Maximum you'd pay per token (you profit if success probability > price/$100)

The clearing price will be set to the highest bid received."""
        else:
            market_info = ""
            if goal and goal.base_price is not None:
                market_info = f"\nCurrent market price: ${goal.base_price:.2f}"
            market_context = f"""TRADING ROUND (Market Update):
This is a follow-up trading round. A market price has been established.{market_info}
You can buy at your bid price or sell at your ask price."""
            task_description = """Your task: Provide an updated analysis based on new information, then post your bid/ask prices.

First, provide your updated analysis (2-3 sentences on any new information, how it changes your view):

Then, set your bid/ask prices for success tokens:
- Buy price: Maximum you'd pay per token (you profit if success probability > price/$100)
- Sell price: Minimum you'd accept per token (you profit if you think success probability < price/$100)"""

        if is_auction:
            reply_format = """Reply with your analysis, then ONLY:
<buy>$X.XX</buy>"""
        else:
            reply_format = """Reply with your analysis, then ONLY:
<buy>$X.XX</buy>
<sell>$Y.YY</sell>"""

        prompt = f"""You are {agent.name}, a profit-maximizing AI agent trading prediction contracts. Today is {current_date}.

MARKET RULES:
- If the goal succeeds: each success token pays out $100
- If the goal fails: each success token pays out $0
- You trade tokens at market prices to maximize profit

{market_context}

{goal_context}

{updates_context}

{position_info}

{prev_analysis_context}{task_description}

{reply_format}"""

        agent_prompts.append((agent.id, agent.name, prompt))

    # Run all agent analyses concurrently
    debate_messages = []
    spreads = []

    with ThreadPoolExecutor(max_workers=len(agents)) as executor:
        futures = [
            executor.submit(_process_agent_analysis, agent_id, agent_name, goal_id, update_id, prompt)
            for agent_id, agent_name, prompt in agent_prompts
        ]
        for future in futures:
            debate_msg, spread = future.result()
            if debate_msg:
                debate_messages.append(debate_msg)
            if spread:
                spreads.append(spread)

    return debate_messages, spreads

def get_agent_spreads(goal_id: int, update_id: int, agents: List[Agent]) -> List[AgentSpread]:
    """
    Get buy/sell price spreads from all agents based on debate history.
    Each agent analyzes the full debate and posts their bid/ask spread.
    """
    debate_messages = get_debate_messages(goal_id, update_id)

    if not debate_messages:
        return []

    spreads = []
    goal = get_goal(goal_id)

    if not goal:
        return []

    # Build debate summary
    debate_summary = "Debate Summary:\n"
    for msg in debate_messages:
        agent = get_agent(msg.agent_id)
        agent_name = agent.name if agent else f"Agent {msg.agent_id}"
        debate_summary += f"Round {msg.round_number} - {agent_name}: {msg.content}\n"

    # Build update history (all updates, no truncation)
    updates = get_goal_updates(goal_id)
    update_history = ""
    if updates:
        update_history = "Goal Progress Updates:\n"
        for update in updates:
            update_history += f"- {update.date}: {update.content}\n"
        update_history += "\n"

    # Get the relevant date: update date if this is an update, otherwise today
    if update_id == 0:
        current_date = datetime.now().date().isoformat()
    else:
        update = get_goal_update(update_id)
        current_date = update.date if update else datetime.now().date().isoformat()

    for agent in agents:
        # Get agent's history for context
        agent_history = get_agent_history(agent.id, limit=5)
        history_context = ""
        if agent_history:
            history_context = "Your recent prediction history:\n"
            for i, entry in enumerate(agent_history, 1):
                goal_ref = f"Goal #{entry['goal_id']}"
                pred_range = f"${entry['buy_price']:.2f}-${entry['sell_price']:.2f}"
                market = f"${entry['market_price']:.2f}" if entry['market_price'] else "pending"
                history_context += f"  {i}. {goal_ref}: You predicted {pred_range}, market price was {market}\n"
            history_context += "\n"

        # Get agent's previous analysis if exists
        agent_prev_analysis = agent.analyses.get(str(goal_id), "")
        prev_analysis_context = f"Your previous analysis on this goal: {agent_prev_analysis}\n\n" if agent_prev_analysis else ""

        prompt = f"""You are {agent.name}. Today is {current_date}. After the following debate about a goal:

Goal: {goal.description}
Target Date: {goal.target_date}

{update_history}{history_context}{prev_analysis_context}{debate_summary}

Based on this discussion, what are your bid/ask prices for success tokens?

Think about the debate points and estimate:
- Buy price: Maximum you'd pay per token (probability * $100)
- Sell price: Minimum you'd accept per token

Reply with ONLY:
<buy>$X.XX</buy>
<sell>$Y.YY</sell>"""

        response = send_openrouter([{"role": "user", "content": prompt}])

        if response:
            buy_match = re.search(r'<buy>\$?([\d.]+)</buy>', response)
            sell_match = re.search(r'<sell>\$?([\d.]+)</sell>', response)

            if buy_match and sell_match:
                buy_price = float(buy_match.group(1))
                sell_price = float(sell_match.group(1))
                spreads.append(AgentSpread(
                    agent_id=agent.id,
                    buy_price=buy_price,
                    sell_price=sell_price
                ))

    return spreads

def conduct_auction(goal_id: int, update_id: int = 0, num_agents: int = 3):
    """
    Conduct a full market auction for a goal.
    Orchestrates: single-round debate with pricing → order matching → settlement

    Args:
        goal_id: Goal being auctioned
        update_id: Market event ID (0 for initial goal creation, >0 for updates)
        num_agents: How many agents to use (default 3)
    """
    goal = get_goal(goal_id)
    if not goal:
        print(f"Goal {goal_id} not found")
        return

    print(f"\n=== Starting Auction for Goal #{goal_id} ===", flush=True)

    # Get all available agents (or create if needed)
    all_agents = get_all_agents()
    if len(all_agents) < num_agents:
        if len(all_agents) == 0:
            print(f"No agents found. Creating {num_agents} default agents...", flush=True)
            agent_names = ["Alice", "Bob", "Charlie", "Diana", "Eve"]
            for i in range(num_agents):
                agent_id = get_next_id("agent:id")
                new_agent = Agent(
                    id=agent_id,
                    name=f"Agent {agent_names[i]}",
                    cash_balance=1000.0,
                    token_holdings={},
                    created_at=serialize_datetime()
                )
                save_agent(new_agent)
                print(f"  Created Agent {agent_names[i]} (ID: {agent_id})", flush=True)
            all_agents = get_all_agents()
        else:
            print(f"Warning: Only {len(all_agents)} agents available, need {num_agents}", flush=True)

    agents = all_agents[:num_agents]

    if not agents:
        print("Failed to create or find agents for auction", flush=True)
        return

    # Initialize token supply for this goal if first auction
    if update_id == 0:
        initialize_goal_tokens(goal_id, 100)

    # Single debate round with pricing
    print(f"Starting debate and pricing with {len(agents)} agents...", flush=True)
    debate_messages, spreads = conduct_debate_round(goal_id, update_id, agents)

    if not spreads:
        print("No spreads generated, auction failed", flush=True)
        return

    # Store spreads to Redis
    store_agent_spreads(goal_id, update_id, spreads)

    print(f"Received {len(spreads)} spreads from agents", flush=True)
    for spread in spreads:
        print(f"  Agent {spread.agent_id}: buy=${spread.buy_price:.2f}, sell=${spread.sell_price:.2f}", flush=True)

    # Order matching
    print("Matching orders...", flush=True)
    trades = match_orders(spreads)
    print(f"Found {len(trades)} trades to execute", flush=True)

    # If no trades and this is round 0 (initial goal creation), use auction fallback
    if not trades and update_id == 0:
        print("No trades converged. Running auction fallback for market seeding...", flush=True)
        trades = auction_fallback(spreads)
        print(f"Auction fallback produced {len(trades)} trades", flush=True)

    # Settlement
    market_price = None
    if trades:
        print("Settling trades...", flush=True)
        settle_trades(goal_id, trades, update_id)
        print("Trades settled successfully", flush=True)

        # Calculate market price from executed trades
        trade_prices = [trade[2] for trade in trades]  # trade[2] is price_per_token
        if trade_prices:
            market_price = sum(trade_prices) / len(trade_prices)
            print(f"Market price discovered: ${market_price:.2f}", flush=True)
    else:
        print("No trades to settle", flush=True)

    # Update goal with market price
    if market_price is not None:
        goal_obj = get_goal(goal_id)
        if goal_obj:
            goal_obj.base_price = market_price
            save_goal(goal_obj)
            print(f"Updated goal {goal_id} base_price to ${market_price:.2f}", flush=True)

    # Save agent predictions to history
    print("Saving agent prediction history...", flush=True)
    spreads = get_agent_spreads_from_redis(goal_id, update_id)
    for spread in spreads:
        save_agent_history_entry(spread.agent_id, goal_id, update_id, spread, market_price)

    print(f"=== Auction Complete for Goal #{goal_id} ===\n", flush=True)

def resolve_goal_settlement(goal_id: int, outcome: str):
    """
    Settle all agent positions when goal is resolved.
    outcome: "success" or "failure"

    If success: longs win $100/token, shorts lose $100/token
    If failure: shorts win $100/token, longs lose $100/token
    """
    print(f"\n=== Settling Goal #{goal_id} with outcome: {outcome} ===", flush=True)

    agents = get_all_agents()

    for agent in agents:
        token_position = agent.token_holdings.get(str(goal_id), 0)

        if token_position == 0:
            continue  # Skip agents with no position

        # Calculate P&L
        if outcome == "success":
            # Longs win, shorts lose
            pnl = token_position * 100  # Positive for longs, negative for shorts
        else:  # failure
            # Shorts win, longs lose
            pnl = -token_position * 100  # Negative for longs, positive for shorts

        # Update agent cash
        agent.cash_balance += pnl

        # Zero out position
        agent.token_holdings[str(goal_id)] = 0

        # Save updated agent
        save_agent(agent)

        print(f"  Agent {agent.name} (ID {agent.id}):", flush=True)
        print(f"    Position: {int(token_position)} tokens", flush=True)
        print(f"    P&L: ${pnl:.2f}", flush=True)
        print(f"    New Cash: ${agent.cash_balance:.2f}", flush=True)

    print(f"=== Goal #{goal_id} Settlement Complete ===\n", flush=True)

def estimate_contract_base_price(goal_id: int):
    """Estimate base price for a goal by querying LLM 3 times asynchronously with context and averaging"""
    # Fetch goal details
    goal = get_goal(goal_id)
    if not goal:
        print(f"Goal {goal_id} not found")
        return

    # Calculate days left
    target_date = datetime.fromisoformat(goal.target_date)
    today = datetime.now().date()
    days_left = (target_date.date() - today).days

    # Create detailed prompt with context
    prompt = f"""You are pricing a prediction contract for an accountability agent system.

SYSTEM: We run a service where AI agents trade binary prediction contracts on whether users will achieve their goals. The winner of each contract receives a $100 payout at the resolution date.

USER'S GOAL: {goal.description}
TARGET DATE: {goal.target_date}
DAYS REMAINING: {days_left} days
CONTRACT PAYOUT: $100 (winner takes all)

Your task: Set a fair BASE PRICE for this contract (the initial price at which agents can enter the contract).

Think through the following:
1. What is the probability this goal will be achieved in {days_left} days?
2. Based on that probability, what is the expected value for each side of the contract?
3. What fair price balances both sides so neither has an obvious edge initially?
4. Consider how difficult the goal is and how much time remains.

Based on your analysis, what is a fair base price in USD for this contract?

Reply with your chain of thought reasoning, then end with ONLY an XML tag with the price like this: <price>X.XX</price>"""

    # Make 3 LLM calls in parallel using ThreadPoolExecutor
    prices = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_call_llm_for_price, prompt) for _ in range(3)]
        for future in futures:
            result = future.result()
            if result is not None:
                prices.append(result)

    if prices:
        average_price = sum(prices) / len(prices)
        goal.base_price = average_price
        save_goal(goal)
        print(f"Set base price for goal {goal_id}: ${average_price:.2f} (based on {len(prices)} estimates)")

# Endpoints
@app.post("/goals")
def create_goal(request: CreateGoalRequest, background_tasks: BackgroundTasks) -> Goal:
    """Create a new goal with a target date in DD/MM/YYYY format"""
    # Convert DD/MM/YYYY to ISO format for storage
    target_date_obj = datetime.strptime(request.date, "%d/%m/%Y")
    target_date_iso = target_date_obj.date().isoformat()

    # Create goal
    goal_id = get_next_id("goal:id")
    goal = Goal(
        id=goal_id,
        description=f"{request.goal} (Measurement: {request.measurement})",
        target_date=target_date_iso,
        created_at=serialize_datetime(),
        status="active"
    )

    # Save goal to Redis
    save_goal(goal)

    # Trigger market auction for goal creation (treat as update_id=0)
    background_tasks.add_task(conduct_auction, goal_id, 0, 3)

    return goal

@app.get("/goals")
def list_goals() -> List[Goal]:
    """Retrieve all goals"""
    goal_ids = list(redis_client.smembers("goals:all") or [])  # type: ignore
    if not goal_ids:
        return []

    goals = []
    for goal_id in goal_ids:
        goal = get_goal(int(goal_id))
        if goal:
            goals.append(goal)

    return sorted(goals, key=lambda g: g.id)

@app.get("/goals/{goal_id}")
def get_goal_by_id(goal_id: int) -> Goal:
    """Retrieve a specific goal by ID"""
    print(f"\n=== GET /goals/{goal_id} ===", flush=True)
    data = redis_client.get(f"goal:{goal_id}")
    print(f"Redis data for goal:{goal_id}: {data}", flush=True)
    goal = get_goal(goal_id)
    print(f"Parsed goal: {goal}", flush=True)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal

@app.post("/goals/{goal_id}/updates")
def create_goal_update(goal_id: int, request: CreateGoalUpdateRequest, background_tasks: BackgroundTasks) -> GoalUpdate:
    """Submit an update for a goal"""
    # Verify goal exists
    goal = get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Create update
    update_id = get_next_id("update:id")
    update = GoalUpdate(
        id=update_id,
        goal_id=goal_id,
        content=request.content,
        date=request.date,
        created_at=serialize_datetime()
    )

    # Save update to Redis
    save_goal_update(update)

    # Trigger market auction for goal update
    background_tasks.add_task(conduct_auction, goal_id, update_id, 3)

    return update

@app.get("/goals/{goal_id}/updates")
def get_goal_updates_endpoint(goal_id: int) -> List[GoalUpdate]:
    """Retrieve all updates for a goal"""
    # Verify goal exists
    goal = get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    return get_goal_updates(goal_id)

@app.patch("/goals/{goal_id}/resolve")
def resolve_goal(goal_id: int, request: ResolveGoalRequest) -> Goal:
    """Resolve a goal with success or failure outcome and settle all agent positions"""
    # Verify goal exists
    goal = get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Validate outcome
    if request.outcome not in ["success", "failure"]:
        raise HTTPException(status_code=400, detail="Outcome must be 'success' or 'failure'")

    # Check if already resolved
    if goal.status == "resolved":
        raise HTTPException(status_code=400, detail="Goal already resolved")

    # Update goal
    goal.status = "resolved"
    goal.outcome = request.outcome
    save_goal(goal)

    # Settle all agent positions
    resolve_goal_settlement(goal_id, request.outcome)

    return goal

@app.get("/goals/{goal_id}/updates/{update_id}/market-analysis")
def get_market_analysis(goal_id: int, update_id: int) -> MarketAnalysis:
    """
    Retrieve complete LLM thinking and market analysis for a goal update.
    Returns: debate messages, agent spreads, executed trades, and discovered market price.
    """
    # Verify goal exists
    goal = get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Get the update
    update = get_goal_update(update_id)
    if not update or update.goal_id != goal_id:
        raise HTTPException(status_code=404, detail="Update not found")

    # Retrieve all market data
    debate_messages = get_debate_messages(goal_id, update_id)
    spreads = get_agent_spreads_from_redis(goal_id, update_id)
    trades = get_trades_for_update(goal_id, update_id)

    # Calculate market price from trades
    market_price = None
    if trades:
        prices = [trade.price_per_token for trade in trades]
        if prices:
            market_price = sum(prices) / len(prices)

    # Build trade data with agent names
    trades_with_names = []
    for trade in trades:
        buyer = get_agent(trade.buyer_agent_id)
        seller = get_agent(trade.seller_agent_id)
        trades_with_names.append({
            "buyer_id": trade.buyer_agent_id,
            "buyer_name": buyer.name if buyer else f"Agent {trade.buyer_agent_id}",
            "seller_id": trade.seller_agent_id,
            "seller_name": seller.name if seller else f"Agent {trade.seller_agent_id}",
            "price": trade.price_per_token,
            "quantity": trade.tokens_exchanged,
            "timestamp": trade.created_at
        })

    return MarketAnalysis(
        update_id=update_id,
        update_content=update.content,
        update_date=update.date,
        debate_messages=debate_messages,
        agent_spreads=spreads,
        trades=trades_with_names,
        market_price=market_price
    )

# Agent Endpoints
@app.post("/agents")
def create_agent(request: CreateAgentRequest) -> Agent:
    """Create a new agent with initial cash balance"""
    agent_id = get_next_id("agent:id")
    agent = Agent(
        id=agent_id,
        name=request.name,
        cash_balance=request.cash_balance,
        token_holdings={},
        created_at=serialize_datetime()
    )

    save_agent(agent)
    return agent

@app.get("/agents")
def list_agents() -> List[Agent]:
    """Retrieve all agents"""
    return get_all_agents()

@app.get("/agents/{agent_id}")
def get_agent_by_id(agent_id: int) -> Agent:
    """Retrieve a specific agent by ID"""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
