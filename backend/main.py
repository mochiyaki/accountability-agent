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
    redis_client.set(f"goal:{goal.id}", json.dumps(goal.model_dump()))
    redis_client.sadd("goals:all", goal.id)

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

def settle_trades(goal_id: int, trades: List[tuple]):
    """
    Settle trades by updating agent cash and token holdings.
    trades: list of (buyer_agent_id, seller_agent_id, price_per_token, quantity)
    """
    for buyer_id, seller_id, price, qty in trades:
        buyer = get_agent(buyer_id)
        seller = get_agent(seller_id)

        if not buyer or not seller:
            continue

        # Update cash balances
        buyer.cash_balance -= price * qty
        seller.cash_balance += price * qty

        # Update token holdings
        goal_id_str = str(goal_id)
        buyer.token_holdings[goal_id_str] = buyer.token_holdings.get(goal_id_str, 0) + qty
        seller.token_holdings[goal_id_str] = seller.token_holdings.get(goal_id_str, 0) - qty

        # Save updated agents
        save_agent(buyer)
        save_agent(seller)

        # Record the trade
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
        print("\n" + "="*80)
        print("OPENROUTER REQUEST")
        print("="*80)
        print(f"Model: {model}")
        print(f"Provider: {provider}")
        print(f"Number of messages: {len(messages)}")

        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Accountability Agent",
            "Content-Type": "application/json",
        }

        print("\nHeaders:")
        for key, value in headers.items():
            if key == "Authorization":
                print(f"  {key}: Bearer [REDACTED]")
            else:
                print(f"  {key}: {value}")

        payload = {
            "model": model,
            "messages": messages,
        }

        if provider:
            payload["provider"] = provider

        print("\nPayload:")
        print(f"  model: {payload['model']}")
        if provider:
            print(f"  provider: {payload['provider']}")
        print(f"  messages:")
        for i, msg in enumerate(payload['messages']):
            print(f"    [{i}] role: {msg['role']}")
            content = msg['content']
            if len(content) > 200:
                print(f"        content: {content[:200]}... (truncated, total length: {len(content)})")
            else:
                print(f"        content: {content}")

        print("\nSending to: https://openrouter.ai/api/v1/chat/completions")

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )

        print(f"\nResponse Status: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        print("\nResponse Data:")
        print(f"  Model: {data.get('model')}")
        print(f"  Choices: {len(data.get('choices', []))}")
        print(f"  Usage: {data.get('usage')}")

        message_content = data["choices"][0]["message"]["content"]

        print(f"\nMessage Content:")
        if len(message_content) > 300:
            print(f"  {message_content[:300]}... (truncated, total length: {len(message_content)})")
        else:
            print(f"  {message_content}")

        print("="*80 + "\n")
        return message_content
    except Exception as e:
        print(f"\nError calling OpenRouter: {e}")
        print("="*80 + "\n")
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

def conduct_debate_round(goal_id: int, update_id: int, round_number: int, agents: List[Agent]) -> List[DebateMessage]:
    """
    Conduct a single round of debate where agents analyze and respond.

    Round 1: Independent analysis of the goal
    Round 2: Agents see previous round and respond
    """
    goal = get_goal(goal_id)
    updates = get_goal_updates(goal_id)

    if not goal:
        return []

    # Build context for agents
    goal_context = f"Goal #{goal_id}: {goal.description}\nTarget Date: {goal.target_date}"

    # Build update history
    updates_context = ""
    if updates:
        updates_context = "Recent Updates:\n"
        for update in updates[:5]:  # Last 5 updates for context
            updates_context += f"- {update.date}: {update.content}\n"

    # Build previous round context
    prev_round_context = ""
    if round_number > 1:
        prev_messages = get_debate_by_round(goal_id, update_id, round_number - 1)
        if prev_messages:
            prev_round_context = "\nPrevious Round Analysis:\n"
            for msg in prev_messages:
                agent = get_agent(msg.agent_id)
                agent_name = agent.name if agent else f"Agent {msg.agent_id}"
                prev_round_context += f"- {agent_name}: {msg.content}\n"

    # Each agent generates their analysis
    messages_this_round = []
    for agent in agents:
        # Get agent's previous analysis if exists
        agent_prev_analysis = agent.analyses.get(str(goal_id), "")
        prev_analysis_context = f"Your previous analysis: {agent_prev_analysis}\n" if agent_prev_analysis else ""

        if round_number == 1:
            prompt = f"""You are {agent.name}, an AI analyzing a goal for a prediction market.

{goal_context}
{updates_context}

Your task: Provide an independent analysis of whether this goal will be achieved.
{prev_analysis_context}
Focus on: probability of success, key risks, time remaining, and confidence level.
Be concise (2-3 sentences)."""
        else:
            prompt = f"""You are {agent.name}. Based on the previous round of analysis:

{goal_context}
{prev_round_context}

Now provide your response. Do you agree, disagree, or have new insights?
Consider their arguments and state your updated view on success probability.
Be concise (2-3 sentences)."""

        response = send_openrouter([{"role": "user", "content": prompt}])

        if response:
            store_debate_message(goal_id, update_id, agent.id, round_number, response)
            messages_this_round.append(DebateMessage(
                agent_id=agent.id,
                round_number=round_number,
                content=response,
                timestamp=serialize_datetime()
            ))

    return messages_this_round

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

    for agent in agents:
        prompt = f"""You are {agent.name}. After the following debate about a goal:

Goal: {goal.description}

{debate_summary}

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

def conduct_auction(goal_id: int, update_id: int = 0, num_agents: int = 3, num_rounds: int = 2):
    """
    Conduct a full market auction for a goal.
    Orchestrates: debate → spread generation → order matching → settlement

    Args:
        goal_id: Goal being auctioned
        update_id: Market event ID (0 for initial goal creation, >0 for updates)
        num_agents: How many agents to use (default 3)
        num_rounds: How many debate rounds (default 2)
    """
    goal = get_goal(goal_id)
    if not goal:
        print(f"Goal {goal_id} not found")
        return

    print(f"\n=== Starting Auction for Goal #{goal_id} ===")

    # Get all available agents (or create if needed)
    all_agents = get_all_agents()
    if len(all_agents) < num_agents:
        if len(all_agents) == 0:
            print(f"No agents found. Creating {num_agents} default agents...")
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
                print(f"  Created Agent {agent_names[i]} (ID: {agent_id})")
            all_agents = get_all_agents()
        else:
            print(f"Warning: Only {len(all_agents)} agents available, need {num_agents}")

    agents = all_agents[:num_agents]

    if not agents:
        print("Failed to create or find agents for auction")
        return

    # Initialize token supply for this goal if first auction
    if update_id == 0:
        initialize_goal_tokens(goal_id, 100)

    # Debate rounds
    print(f"Starting debate with {len(agents)} agents for {num_rounds} rounds...")
    for round_num in range(1, num_rounds + 1):
        print(f"  Round {round_num}...")
        conduct_debate_round(goal_id, update_id, round_num, agents)

    # Get spreads from agents
    print("Collecting agent spreads...")
    spreads = get_agent_spreads(goal_id, update_id, agents)

    if not spreads:
        print("No spreads generated, auction failed")
        return

    print(f"Received {len(spreads)} spreads from agents")
    for spread in spreads:
        print(f"  Agent {spread.agent_id}: buy=${spread.buy_price:.2f}, sell=${spread.sell_price:.2f}")

    # Order matching
    print("Matching orders...")
    trades = match_orders(spreads)
    print(f"Found {len(trades)} trades to execute")

    # Settlement
    if trades:
        print("Settling trades...")
        settle_trades(goal_id, trades)
        print("Trades settled successfully")

    print(f"=== Auction Complete for Goal #{goal_id} ===\n")

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
    background_tasks.add_task(conduct_auction, goal_id, 0, 3, 2)

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
    goal = get_goal(goal_id)
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
    background_tasks.add_task(conduct_auction, goal_id, update_id, 3, 2)

    return update

@app.get("/goals/{goal_id}/updates")
def get_goal_updates_endpoint(goal_id: int) -> List[GoalUpdate]:
    """Retrieve all updates for a goal"""
    # Verify goal exists
    goal = get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    return get_goal_updates(goal_id)

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
