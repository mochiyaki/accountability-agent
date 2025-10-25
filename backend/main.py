from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date

app = FastAPI(title="Accountability Agent API", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class Goal(BaseModel):
    id: Optional[int] = None
    description: str
    target_date: date
    created_at: Optional[datetime] = None
    status: Optional[str] = "active"  # active, completed, failed

class DailyTask(BaseModel):
    id: Optional[int] = None
    goal_id: int
    description: str
    assigned_date: date
    completed: bool = False
    created_at: Optional[datetime] = None

class Agent(BaseModel):
    id: Optional[int] = None
    name: str
    token_balance: int = 100
    created_at: Optional[datetime] = None

class Contract(BaseModel):
    id: Optional[int] = None
    goal_id: int
    agent_id: int
    prediction: float  # 0-1, likelihood of success
    tokens_at_stake: int
    created_at: Optional[datetime] = None
    status: Optional[str] = "active"  # active, resolved

class Trade(BaseModel):
    id: Optional[int] = None
    contract_id: int
    buyer_agent_id: int
    seller_agent_id: int
    tokens_exchanged: int
    created_at: Optional[datetime] = None

# In-memory storage
goals_db: List[Goal] = []
tasks_db: List[DailyTask] = []
agents_db: List[Agent] = []
contracts_db: List[Contract] = []
trades_db: List[Trade] = []

next_goal_id = 1
next_task_id = 1
next_agent_id = 1
next_contract_id = 1
next_trade_id = 1

# Routes
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to Accountability Agent API",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now()}

# Goal endpoints
@app.post("/goals", response_model=Goal, status_code=201)
async def create_goal(goal: Goal):
    """Create a new goal"""
    global next_goal_id
    new_goal = Goal(
        id=next_goal_id,
        description=goal.description,
        target_date=goal.target_date,
        created_at=datetime.now(),
        status="active"
    )
    goals_db.append(new_goal)
    next_goal_id += 1
    return new_goal

@app.get("/goals/{goal_id}", response_model=Goal)
async def get_goal(goal_id: int):
    """Get goal details"""
    for goal in goals_db:
        if goal.id == goal_id:
            return goal
    raise HTTPException(status_code=404, detail="Goal not found")

@app.get("/goals", response_model=List[Goal])
async def list_goals():
    """List all goals"""
    return goals_db

# Task endpoints
@app.post("/goals/{goal_id}/generate-tasks", status_code=201)
async def generate_daily_tasks(goal_id: int):
    """Agent generates daily tasks for a goal"""
    # Check goal exists
    goal = None
    for g in goals_db:
        if g.id == goal_id:
            goal = g
            break
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Dummy task generation
    global next_task_id
    dummy_tasks = [
        "Research and plan approach",
        "Complete first milestone",
        "Review progress and adjust",
        "Execute core tasks",
        "Wrap up and document"
    ]

    created_tasks = []
    for task_desc in dummy_tasks:
        new_task = DailyTask(
            id=next_task_id,
            goal_id=goal_id,
            description=task_desc,
            assigned_date=date.today(),
            completed=False,
            created_at=datetime.now()
        )
        tasks_db.append(new_task)
        created_tasks.append(new_task)
        next_task_id += 1

    return {"goal_id": goal_id, "tasks": created_tasks, "count": len(created_tasks)}

@app.get("/goals/{goal_id}/daily-tasks", response_model=List[DailyTask])
async def get_daily_tasks(goal_id: int):
    """Get tasks for a goal"""
    return [t for t in tasks_db if t.goal_id == goal_id]

@app.post("/goals/{goal_id}/complete-task/{task_id}")
async def complete_task(goal_id: int, task_id: int):
    """Mark a task as complete"""
    for task in tasks_db:
        if task.id == task_id and task.goal_id == goal_id:
            task.completed = True
            return {"message": "Task completed", "task": task}
    raise HTTPException(status_code=404, detail="Task not found")

# Agent endpoints
@app.post("/agents", response_model=Agent, status_code=201)
async def register_agent(agent: Agent):
    """Register a new agent"""
    global next_agent_id
    new_agent = Agent(
        id=next_agent_id,
        name=agent.name,
        token_balance=agent.token_balance or 100,
        created_at=datetime.now()
    )
    agents_db.append(new_agent)
    next_agent_id += 1
    return new_agent

@app.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: int):
    """Get agent details"""
    for agent in agents_db:
        if agent.id == agent_id:
            return agent
    raise HTTPException(status_code=404, detail="Agent not found")

@app.get("/agents")
async def list_agents():
    """List all agents"""
    return agents_db

# Contract endpoints
@app.post("/goals/{goal_id}/contracts", response_model=Contract, status_code=201)
async def create_contract(goal_id: int, contract: Contract):
    """Agent creates a contract (prediction) on a goal"""
    global next_contract_id

    # Verify goal exists
    goal = None
    for g in goals_db:
        if g.id == goal_id:
            goal = g
            break
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Verify agent exists
    agent = None
    for a in agents_db:
        if a.id == contract.agent_id:
            agent = a
            break
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_contract = Contract(
        id=next_contract_id,
        goal_id=goal_id,
        agent_id=contract.agent_id,
        prediction=contract.prediction,
        tokens_at_stake=contract.tokens_at_stake,
        created_at=datetime.now(),
        status="active"
    )
    contracts_db.append(new_contract)
    next_contract_id += 1
    return new_contract

@app.get("/goals/{goal_id}/contracts", response_model=List[Contract])
async def get_goal_contracts(goal_id: int):
    """Get all contracts on a goal"""
    return [c for c in contracts_db if c.goal_id == goal_id]

@app.get("/contracts/{contract_id}", response_model=Contract)
async def get_contract(contract_id: int):
    """Get contract details"""
    for contract in contracts_db:
        if contract.id == contract_id:
            return contract
    raise HTTPException(status_code=404, detail="Contract not found")

# Trade endpoints
@app.post("/contracts/{contract_id}/trade", response_model=Trade, status_code=201)
async def trade_contract(contract_id: int, trade: Trade):
    """Agents trade a contract"""
    global next_trade_id

    # Verify contract exists
    contract = None
    for c in contracts_db:
        if c.id == contract_id:
            contract = c
            break
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Verify agents exist
    buyer = None
    seller = None
    for a in agents_db:
        if a.id == trade.buyer_agent_id:
            buyer = a
        if a.id == trade.seller_agent_id:
            seller = a
    if not buyer or not seller:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check balance
    if seller.token_balance < trade.tokens_exchanged:
        raise HTTPException(status_code=400, detail="Seller insufficient tokens")

    # Execute trade
    seller.token_balance -= trade.tokens_exchanged
    buyer.token_balance += trade.tokens_exchanged

    new_trade = Trade(
        id=next_trade_id,
        contract_id=contract_id,
        buyer_agent_id=trade.buyer_agent_id,
        seller_agent_id=trade.seller_agent_id,
        tokens_exchanged=trade.tokens_exchanged,
        created_at=datetime.now()
    )
    trades_db.append(new_trade)
    next_trade_id += 1
    return new_trade

@app.get("/agents/{agent_id}/balance")
async def get_agent_balance(agent_id: int):
    """Get agent token balance"""
    for agent in agents_db:
        if agent.id == agent_id:
            return {"agent_id": agent_id, "balance": agent.token_balance}
    raise HTTPException(status_code=404, detail="Agent not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
