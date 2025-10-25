import json
import redis
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from typing import List, Optional
from datetime import datetime, date

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

# Endpoints
@app.post("/goals")
def create_goal(request: CreateGoalRequest) -> dict:
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
