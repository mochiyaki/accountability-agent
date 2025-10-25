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
    created_at: Optional[str] = None

class Trade(BaseModel):
    id: Optional[int] = None
    goal_id: int
    buyer_agent_id: int
    seller_agent_id: int
    tokens_exchanged: int
    created_at: Optional[str] = None

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
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Accountability Agent",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
        }

        if provider:
            payload["provider"] = provider

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )

        response.raise_for_status()
        data = response.json()
        message_content = data["choices"][0]["message"]["content"]
        return message_content
    except Exception as e:
        print(f"Error calling OpenRouter: {e}")
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

    # Estimate base price for goal in background
    background_tasks.add_task(estimate_contract_base_price, goal_id)

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
def create_goal_update(goal_id: int, request: CreateGoalUpdateRequest) -> GoalUpdate:
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
