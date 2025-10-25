// src/api.ts
export type Goal = {
  id: number;
  description: string;
  target_date: string; // ISO YYYY-MM-DD
  created_at?: string | null;
  status?: "active" | "resolved";
  payout_amount?: number;
  outcome?: string | null;
  base_price?: number | null;
};

export type GoalUpdate = {
  id: number;
  goal_id: number;
  content: string;
  date: string; // ISO
  created_at?: string | null;
};

export type DebateMessage = {
  agent_id: number;
  round_number: number;
  content: string;
  timestamp: string;
};

export type AgentSpread = {
  agent_id: number;
  buy_price: number;
  sell_price: number;
};

export type TradeRecord = {
  buyer_id: number;
  buyer_name: string;
  seller_id: number;
  seller_name: string;
  price: number;
  quantity: number;
  timestamp?: string;
};

export type MarketAnalysis = {
  update_id: number;
  update_content: string;
  update_date: string;
  debate_messages: DebateMessage[];
  agent_spreads: AgentSpread[];
  trades: TradeRecord[];
  market_price?: number | null;
};

const defaultApiBase = (import.meta.env.VITE_API_BASE as string) || "http://127.0.0.1:8000";

function baseUrl(apiBase?: string) {
  return (apiBase || defaultApiBase).replace(/\/+$/, "");
}

export async function listGoals(apiBase?: string) {
  const res = await fetch(`${baseUrl(apiBase)}/goals`);
  if (!res.ok) throw new Error(`GET /goals -> ${res.status}`);
  return (await res.json()) as Goal[];
}

export async function createGoal(payload: { goal: string; measurement: string; date: string }, apiBase?: string) {
  const res = await fetch(`${baseUrl(apiBase)}/goals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`POST /goals -> ${res.status} ${txt}`);
  }
  return (await res.json()) as Goal;
}

export async function getGoal(goalId: number, apiBase?: string) {
  const res = await fetch(`${baseUrl(apiBase)}/goals/${goalId}`);
  if (!res.ok) throw new Error(`GET /goals/${goalId} -> ${res.status}`);
  return (await res.json()) as Goal;
}

export async function listGoalUpdates(goalId: number, apiBase?: string) {
  const res = await fetch(`${baseUrl(apiBase)}/goals/${goalId}/updates`);
  if (!res.ok) throw new Error(`GET /goals/${goalId}/updates -> ${res.status}`);
  return (await res.json()) as GoalUpdate[];
}

export async function createGoalUpdate(goalId: number, payload: { content: string; date: string }, apiBase?: string) {
  const res = await fetch(`${baseUrl(apiBase)}/goals/${goalId}/updates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`POST /goals/${goalId}/updates -> ${res.status} ${txt}`);
  }
  return (await res.json()) as GoalUpdate;
}

export async function getMarketAnalysis(goalId: number, updateId: number, apiBase?: string) {
  const res = await fetch(`${baseUrl(apiBase)}/goals/${goalId}/updates/${updateId}/market-analysis`);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`GET /goals/${goalId}/updates/${updateId}/market-analysis -> ${res.status} ${txt}`);
  }
  return (await res.json()) as MarketAnalysis;
}

export async function listAgents(apiBase?: string) {
  const res = await fetch(`${baseUrl(apiBase)}/agents`);
  if (!res.ok) throw new Error(`GET /agents -> ${res.status}`);
  return (await res.json()) as { id: number; name: string }[];
}
