# Accountability Agent Backend - Handover Document

## Project Overview

**Accountability Agent** is a FastAPI-based system that uses AI agents to trade binary prediction contracts on whether users will achieve their goals. The system tracks goals, automatically generates daily tasks, and enables multi-agent trading markets around goal achievement outcomes.

### Core Concept
- Users set **goals** with target dates and measurement criteria
- A single LLM agent generates **daily tasks** to help achieve goals
- Multiple LLM agents trade **contracts** (binary prediction instruments) betting on goal success/failure
- Contracts are worth **$100** to the winner at resolution date
- The system uses **chain-of-thought LLM reasoning** to fairly price contracts based on goal context and probability

---

## Architecture Overview

### Technology Stack
- **Framework**: FastAPI with Uvicorn ASGI server
- **Storage**: Redis Cloud (persistent key-value store with JSON serialization)
- **LLM**: OpenRouter API (supporting multiple open-source models)
- **Validation**: Pydantic V2
- **Package Manager**: uv (Python package management)

### Key Design Patterns
1. **Redis Key Pattern**: `resource:id` (e.g., `goal:1`, `contract:5`)
2. **Redis Sets**: `{resource}:all` to track all IDs (e.g., `goals:all`, `contracts:all`)
3. **Async Pricing**: Background tasks return 200 immediately while LLM pricing runs
4. **Chain-of-Thought**: LLM reasoning before final price in XML tags
5. **Multi-Estimate Averaging**: Query LLM 3x and average for robustness

### Data Model Relationships
```
Goal (unified Goal + Contract)
├── id (auto-increment via Redis INCR)
├── description (goal + measurement combined)
├── target_date (ISO format)
├── status (active, resolved)
├── payout_amount (int, default $100 winner-take-all)
├── outcome (null, "success", or "failure")
├── base_price (float, initially null, set by LLM pricing)
└── created_at (ISO timestamp)

No separate Contract model - Goal IS the contract
```

---

## File Structure

### `backend/main.py` (Primary Application)
**~260 lines** - Contains all core API logic

**Key Sections:**

1. **Imports & Setup**
   - FastAPI app initialization
   - CORS middleware (allows all origins)
   - Redis connection with Cloud credentials
   - OpenAI client for OpenRouter API

2. **Data Models** (Pydantic)
   - `Goal`: Unified goal/contract with description, target_date, status, payout_amount, outcome, base_price
   - `DailyTask`: Future - for daily task tracking
   - `Agent`: Future - for agent management
   - `Trade`: Future - for agent trades (references goal_id instead of contract_id)
   - `CreateGoalRequest`: Request validation with DD/MM/YYYY date format

3. **Helper Functions**
   - `get_next_id(key)`: Atomic ID generation via Redis INCR
   - `serialize_datetime()`: ISO format timestamp
   - `get_goal(goal_id)`: Fetch goal from Redis
   - `get_agent(agent_id)`: Fetch agent from Redis
   - `save_agent(agent)`: Persist agent to Redis
   - `save_goal(goal)`: Persist goal to Redis

4. **LLM Goal Pricing** (`estimate_contract_base_price`)
   - Runs as background task (non-blocking)
   - Fetches goal context (no separate contract lookup needed)
   - Calculates `days_left` from target date
   - Creates detailed chain-of-thought prompt asking LLM to:
     - Estimate goal achievement probability
     - Calculate expected value per side
     - Determine fair balancing price
     - Consider difficulty and time factors
   - Queries LLM 3 times with `openai/gpt-5-mini` model
   - Extracts price from XML tags using regex: `<price>X.XX</price>`
   - Averages 3 estimates and updates goal's `base_price` field in Redis

5. **Endpoints**
   - `POST /goals`: Create goal + spawn background pricing (returns Goal)
   - `GET /goals`: List all goals from Redis
   - `GET /goals/{goal_id}`: Fetch specific goal by ID (useful for polling price completion)

**Notable Code Pattern:**
```python
# Date validation with Pydantic
@field_validator("date")
@classmethod
def validate_date_format(cls, v: str) -> str:
    try:
        datetime.strptime(v, "%d/%m/%Y")
        return v
    except ValueError:
        raise ValueError("Date must be in DD/MM/YYYY format")
```

**Background Task Pattern:**
```python
background_tasks.add_task(estimate_contract_base_price, contract_id)
# Returns 200 immediately, pricing happens async
```

### `backend/.env` (Environment Variables - DO NOT COMMIT)
Required for running the application:
```
REDIS_HOST=redis-17532.c10.us-east-1-2.ec2.redns.redis-cloud.com
REDIS_PORT=17532
REDIS_USERNAME=default
REDIS_PASSWORD=<your-password>
OPENROUTER_API_KEY=<your-api-key>
```

**Setup Instructions:**
1. Create `.env` file in backend directory
2. Add Redis Cloud credentials (host, port, username, password)
3. Add OpenRouter API key
4. Never commit to git (listed in .gitignore)

### `backend/.gitignore`
```
.claude/*
```
Prevents committing `.claude` directory which contains local configuration.

### `backend/test_openrouter.py`
Quick test script to verify OpenRouter API integration works:
- Initializes OpenAI client pointing to OpenRouter
- Sends simple prompt: "Say hi. Reply with only one word."
- Uses free model: `z-ai/glm-4.5-air:free`

**Run with:** `python test_openrouter.py`

### `backend/pyproject.toml`
Project configuration and dependencies:
```
requires-python = ">=3.13"
dependencies = [
    "dotenv>=0.9.9",
    "fastapi>=0.120.0",
    "openai>=2.6.1",
    "redis>=7.0.0",
    "uvicorn>=0.38.0",
]
```

---

## How to Run

### Prerequisites
- Python 3.13+
- uv package manager
- Redis Cloud credentials
- OpenRouter API key

### Setup
1. Navigate to backend directory
2. Create `.env` file with credentials (see .env section above)
3. Install dependencies: `uv sync`

### Start Server
```bash
uvicorn main:app --reload
```
Server runs on `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Test API

**Create a goal with contract:**
```bash
curl -X POST http://localhost:8000/goals \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Complete project proposal",
    "measurement": "Submit 10-page document",
    "date": "31/12/2025"
  }'
```

**Response example:**
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

**List all goals:**
```bash
curl http://localhost:8000/goals
```

**Get specific goal (useful for polling price):**
```bash
curl http://localhost:8000/goals/1
```
Response will include `base_price` once LLM pricing is done (initially null)

### Monitor Background Pricing
- Server logs will show when LLM pricing estimates are generated
- Prices are stored in the Goal object's `base_price` field
- Poll `GET /goals/{id}` until `base_price` is no longer null
- Or check directly in Redis: `redis-cli GET goal:1` and look for the base_price field

### Type Checking
```bash
cd backend
uv tool run ty check .
```

---

## Key Technical Decisions

### 1. Redis for Storage
**Why:** Enables fast caching, atomic ID generation, and persistence without database setup complexity. JSON serialization pattern allows storing complex objects.

### 2. Unified Goal Model (Goal = Contract)
**Why:** The 1-to-1 relationship between goals and contracts was redundant. Merging them simplifies:
- Single Redis key per item (`goal:id` instead of `goal:id` + `contract:id`)
- Cleaner API responses (return Goal instead of {goal, contract})
- Fewer helper functions (no get_contract/save_contract)
- Simpler frontend data model

### 3. Background Tasks for LLM Pricing
**Why:** Prevents blocking HTTP responses. Users get immediate 200 response while pricing happens asynchronously. Critical for good UX.
- Frontend polls `GET /goals/{id}` until `base_price` is populated

### 4. Chain-of-Thought Prompting
**Why:** Forces LLM to reason through pricing logic, producing more thoughtful and consistent estimates vs. direct price requests.

### 5. 3x Estimate Averaging
**Why:** Reduces variance from any single LLM call. Averaging 3 independent estimates is more robust to LLM hallucinations or off-day estimates.

### 6. Regex for Price Extraction
**Why:** Lightweight, reliable extraction of `<price>X.XX</price>` format without full XML parsing overhead.

### 7. Type Ignore on Redis smembers()
**Why:** Type checker struggles with redis_client.smembers() return type due to complex inference with decode_responses=True. The `# type: ignore` comment suppresses the false positive without losing other type checking benefits.

---

## Current Implementation Status

### ✅ Completed
- [x] FastAPI application setup with CORS
- [x] Redis Cloud integration with environment variables
- [x] Pydantic models for Goal (unified), DailyTask, Agent, Trade
- [x] POST /goals endpoint with:
  - DD/MM/YYYY date validation
  - Single Goal object creation (no separate contract)
  - Background task spawning for pricing
- [x] GET /goals endpoint with Redis retrieval
- [x] GET /goals/{goal_id} endpoint for polling price completion
- [x] OpenRouter LLM integration
- [x] estimate_contract_base_price() background task with:
  - 3x LLM calls
  - Chain-of-thought prompting
  - Regex price extraction
  - Average calculation
  - Goal object update with base_price
- [x] Unified Goal/Contract model reducing Redis keys and API complexity
- [x] .gitignore setup
- [x] Git commits with clean history

### 🚧 Partially Complete
- [ ] Frontend updated to use new Goal model (App.tsx still expects {goal, contract})
- [ ] DailyTask generation endpoint (model exists, endpoint not implemented)
- [ ] Agent registration and management (model exists, endpoints not implemented)
- [ ] Trade endpoints for contract betting (model exists, endpoints not implemented)
- [ ] Goal resolution logic (outcome settlement)

### ❌ Not Started
- [ ] Price updates as contract trades occur
- [ ] Agent token balance management
- [ ] Trade settlement and payout logic
- [ ] Goal completion tracking
- [ ] Daily task completion tracking
- [ ] Contract history and analytics
- [ ] Error handling and validation edge cases
- [ ] Rate limiting
- [ ] Authentication/authorization
- [ ] Testing suite

---

## Common Tasks

### Add a New Endpoint
1. Create request/response models in main.py (if needed)
2. Define the route function with appropriate method decorator
3. Use helper functions (get_goal, save_contract, etc.)
4. Add background_tasks parameter if async work needed
5. Test with curl command
6. Run type check: `uv tool run ty check .`

### Update LLM Prompts
- Edit the prompt string in `estimate_contract_base_price()` function
- Change model name in `llm_client.chat.completions.create(model="...")`
- Remember to update extraction regex if changing XML tag format

### Debug Redis Keys
```bash
# Connect to Redis
redis-cli -h redis-17532.c10.us-east-1-2.ec2.redns.redis-cloud.com \
  -p 17532 \
  -u default:<password>

# View all keys
KEYS *

# Get specific goal (includes base_price field)
GET goal:1

# View set members
SMEMBERS goals:all

# Check pricing status (will show null initially, then float after LLM runs)
GET goal:1 | jq '.base_price'
```

### Monitor Application
- Server logs show pricing estimates and errors
- Redis CLI shows persisted data
- FastAPI docs at /docs show all endpoints with try-it-out interface

---

## Troubleshooting

### Redis Connection Fails
- Verify .env file has correct credentials
- Check Redis Cloud status (may need to whitelist IP)
- Try connecting with redis-cli directly to confirm credentials

### LLM Pricing Takes Too Long
- Check server logs for rate limiting from OpenRouter
- May need to retry with different model
- Check OpenRouter account balance/quota

### Type Checking Fails
- Run `uv tool run ty check .` to see full error
- Most errors can be fixed with `# type: ignore` comments
- Avoid overly complex type annotations

### Goals/Contracts Not Persisting
- Verify Redis connection is working
- Check that save_goal() and save_contract() are being called
- Verify Redis has sufficient memory

---

## Architecture Diagram

```
User (Frontend)
  ↓
POST /goals {goal, measurement, date}
  ↓
[FastAPI Validation]
  ├─ Create Goal (Redis) with base_price: null
  ├─ Return Goal immediately (200 OK)
  └─ Spawn Background Task
       ↓
    [Background: estimate_contract_base_price()]
       ├─ Fetch Goal from Redis
       ├─ Query LLM (attempt 1)
       ├─ Query LLM (attempt 2)
       ├─ Query LLM (attempt 3)
       ├─ Extract prices via regex
       ├─ Average 3 estimates
       └─ Update Goal.base_price in Redis

Frontend (Polling)
  ↓
GET /goals/{id}
  ↓
[Loop until base_price != null]
  └─ Return Goal with base_price

GET /goals
  ↓
[Retrieve all from Redis]
  └─ Return all goals
```

---

## Environment Setup Checklist

- [ ] Redis Cloud account created
- [ ] .env file created with Redis credentials
- [ ] OpenRouter API key obtained
- [ ] .env file added to .gitignore
- [ ] Dependencies installed via `uv sync`
- [ ] Server starts without errors: `uvicorn main:app --reload`
- [ ] Test endpoint works: `curl http://localhost:8000/goals`
- [ ] Type checking passes: `uv tool run ty check .`

---

## Next Developer Notes

### Important Conventions
1. Always use `model_dump()` not `.dict()` (Pydantic V2)
2. Store objects in Redis as JSON: `json.dumps(object.model_dump())`
3. Retrieve with: `json.loads(redis_client.get(key))`
4. Use atomic ID generation: `get_next_id("resource:id")`
5. Track collections in sets: `redis_client.sadd("resources:all", id)`
6. Goal IS the contract - no separate contract model or storage

### Code Style
- Use type hints on function parameters and returns
- Add docstrings to helper functions
- Use comments for non-obvious logic
- Hackathon mode: Types are optional (not required to run)

### Frontend Integration Notes
- POST /goals now returns just Goal (not {goal, contract})
- Frontend should poll GET /goals/{id} to check base_price completion
- Goal type includes: id, description, target_date, status, payout_amount, outcome, base_price
- Update App.tsx to match the unified Goal model

### Git Workflow
1. Make changes
2. Test locally
3. Commit with clear message: `git commit -m "description"`
4. Never force push to main

### Testing
- Use FastAPI docs at http://localhost:8000/docs for interactive testing
- Write curl commands for manual testing
- Frontend polling pattern: while (goal.base_price === null) { wait 1s; fetch /goals/{id} }

---

## Contact/Questions

Refer to this handover document for architecture understanding. For specific questions about implementation details, check the inline code comments in main.py or this document's "How to Run" and "Common Tasks" sections.

---

**Last Updated:** 2025-10-25
**Version:** 0.2.0
**Status:** Development - Core APIs functional with unified Goal/Contract model, Frontend out of sync (needs update), Agent trading features pending

### Recent Changes (v0.2.0)
- Merged Goal and Contract into single unified Goal model
- Removed separate Contract storage and helper functions
- Added GET /goals/{goal_id} endpoint for polling
- Simplified pricing to update Goal.base_price directly
- Reduced Redis keys: one goal key per item instead of separate contract keys
