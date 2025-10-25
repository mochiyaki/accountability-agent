import json
import redis
import os
import re
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from typing import List, Optional
from datetime import datetime, date
from openai import OpenAI

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

# OpenAI client for OpenRouter
llm_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# Data models
class Goal(BaseModel):
    id: Optional[int] = None
    description: str
    target_date: str  # ISO format date string
    created_at: Optional[str] = None
    status: Optional[str] = "active"  # active, completed, failed

class DailyTask(BaseModel):
    id: Optional[int] = None
    goal_id: int
    description: str
    assigned_date: str  # ISO format date string
    completed: bool = False
    created_at: Optional[str] = None

class Agent(BaseModel):
    id: Optional[int] = None
    name: str
    token_balance: int = 100
    created_at: Optional[str] = None

class Contract(BaseModel):
    id: Optional[int] = None
    goal_id: int
    created_at: Optional[str] = None
    status: Optional[str] = "active"  # active, resolved
    payout_amount: int = 100
    outcome: Optional[str] = None  # success, failure, null if unresolved

class Trade(BaseModel):
    id: Optional[int] = None
    contract_id: int
    buyer_agent_id: int
    seller_agent_id: int
    tokens_exchanged: int
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

def get_contract(contract_id: int) -> Optional[Contract]:
    """Fetch contract from Redis"""
    data = redis_client.get(f"contract:{contract_id}")
    if not data:
        return None
    return Contract(**json.loads(data))

def save_agent(agent: Agent):
    """Save agent to Redis"""
    redis_client.set(f"agent:{agent.id}", json.dumps(agent.model_dump()))
    redis_client.sadd("agents:all", agent.id)

def save_contract(contract: Contract):
    """Save contract to Redis"""
    redis_client.set(f"contract:{contract.id}", json.dumps(contract.model_dump()))
    redis_client.sadd("contracts:all", contract.id)

def estimate_contract_base_price(contract_id: int):
    """Estimate base price for a contract by querying LLM 3 times with context and averaging"""
    # Fetch contract and goal details
    contract = get_contract(contract_id)
    if not contract:
        print(f"Contract {contract_id} not found")
        return

    goal = get_goal(contract.goal_id)
    if not goal:
        print(f"Goal {contract.goal_id} not found")
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

    prices = []

    for _ in range(3):
        try:
            completion = llm_client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Accountability Agent",
                },
                model="openai/gpt-5-mini",
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            response = completion.choices[0].message.content
            match = re.search(r'<price>([\d.]+)</price>', response)
            if match:
                price = float(match.group(1))
                prices.append(price)
                print(f"Estimated price: ${price}")
        except Exception as e:
            print(f"Error estimating price: {e}")

    if prices:
        average_price = sum(prices) / len(prices)
        redis_client.set(f"contract:{contract_id}:base_price", json.dumps({"price": average_price, "days_left": days_left}))
        print(f"Set base price for contract {contract_id}: ${average_price:.2f} (based on {len(prices)} estimates)")

# Endpoints
@app.post("/goals")
def create_goal(request: CreateGoalRequest, background_tasks: BackgroundTasks) -> dict:
    """Create a new goal with a target date in DD/MM/YYYY format and a contract"""
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
    redis_client.set(f"goal:{goal_id}", json.dumps(goal.model_dump()))
    redis_client.sadd("goals:all", goal_id)

    # Create contract for the goal
    contract_id = get_next_id("contract:id")
    contract = Contract(
        id=contract_id,
        goal_id=goal_id,
        created_at=serialize_datetime(),
        status="active"
    )

    # Save contract to Redis
    save_contract(contract)

    # Estimate base price for contract in background
    background_tasks.add_task(estimate_contract_base_price, contract_id)

    return {"goal": goal, "contract": contract}

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
