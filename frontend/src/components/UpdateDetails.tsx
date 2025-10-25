// src/components/UpdateDetails.tsx
import React, { useEffect, useState, useRef } from "react";
// import type { MarketAnalysis, GoalUpdate, Goal, DebateMessage, AgentSpread, TradeRecord } from "../api";
import type { MarketAnalysis, GoalUpdate, Goal, DebateMessage } from "../api";
import { getMarketAnalysis, createGoalUpdate, listGoalUpdates, getGoal, listAgents } from "../api";

type Props = {
  apiBase?: string;
  goal: Goal;
  initialUpdates: GoalUpdate[]; // timeline items
  onGoalUpdated?: (goal: Goal) => void; // called when base_price updated
  refreshGoalList?: () => void;
};

export default function UpdateDetails({ apiBase, goal, initialUpdates, onGoalUpdated, refreshGoalList }: Props) {
  const [updates, setUpdates] = useState<GoalUpdate[]>(initialUpdates || []);
  const [selectedUpdate, setSelectedUpdate] = useState<GoalUpdate | null>(updates[0] || null);
  const [analysis, setAnalysis] = useState<MarketAnalysis | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [polling, setPolling] = useState(false);
  const pollingRef = useRef<number | null>(null);

  const [newText, setNewText] = useState("");
  const [newDate, setNewDate] = useState<string>(""); // YYYY-MM-DD
  const [agentsMap, setAgentsMap] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  // load agents (names) once
  useEffect(() => {
    (async () => {
      try {
        const agents = await listAgents(apiBase);
        const map: Record<number, string> = {};
        agents.forEach((a) => (map[a.id] = a.name));
        setAgentsMap(map);
      } catch {
        // ignore - agent names are optional
      }
    })();
  }, [apiBase]);

  useEffect(() => {
    // refresh local updates if parent changed
    setUpdates(initialUpdates || []);
    if (initialUpdates && initialUpdates.length > 0) {
      setSelectedUpdate(initialUpdates[0]);
    } else {
      setSelectedUpdate(null);
      setAnalysis(null);
    }
  }, [initialUpdates]);

  useEffect(() => {
    // when selected update changes, fetch its analysis (and poll if needed)
    if (!selectedUpdate) {
      setAnalysis(null);
      stopPolling();
      return;
    }
    fetchAnalysis(selectedUpdate.id, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedUpdate]);

  useEffect(() => {
    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshUpdates() {
    try {
      const list = await listGoalUpdates(goal.id, apiBase);
      setUpdates(list);
      // if selected update is missing, close selection
      if (selectedUpdate) {
        const found = list.find((u) => u.id === selectedUpdate.id);
        if (!found) setSelectedUpdate(null);
      }
    } catch (e: any) {
      // ignore
    }
  }

  async function fetchAnalysis(updateId: number, startPollingIfNotDone = false) {
    setError(null);
    setLoadingAnalysis(true);
    stopPolling();
    try {
      const result = await getMarketAnalysis(goal.id, updateId, apiBase);
      setAnalysis(result);
      // determine if analysis is "complete"
      const complete = isAnalysisComplete(result);
      if (!complete && startPollingIfNotDone) {
        startPolling(updateId);
      } else {
        // if complete, update goal data (base_price may have been updated by backend)
        try {
          const freshGoal = await getGoal(goal.id, apiBase);
          onGoalUpdated?.(freshGoal);
          refreshGoalList?.();
        } catch {
          /* ignore */
        }
      }
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoadingAnalysis(false);
    }
  }

  function isAnalysisComplete(a: MarketAnalysis | null) {
    if (!a) return false;
    // treat as complete if market_price exists OR we've observed debate & spreads
    if (a.market_price != null) return true;
    if ((a.debate_messages?.length ?? 0) > 0 && (a.agent_spreads?.length ?? 0) > 0) return true;
    return false;
  }

  function startPolling(updateId: number) {
    stopPolling();
    setPolling(true);
    // poll every 2s
    pollingRef.current = window.setInterval(async () => {
      try {
        const res = await getMarketAnalysis(goal.id, updateId, apiBase);
        setAnalysis(res);
        if (isAnalysisComplete(res)) {
          stopPolling();
          // update goal base price
          const freshGoal = await getGoal(goal.id, apiBase);
          onGoalUpdated?.(freshGoal);
          refreshGoalList?.();
        }
      } catch {
        // keep polling
      }
    }, 2000);
  }

  function stopPolling() {
    if (pollingRef.current) {
      window.clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setPolling(false);
  }

  async function handlePostUpdate(e?: React.FormEvent) {
    e?.preventDefault();
    setError(null);
    if (!newText.trim()) return setError("Please enter update text");
    if (!newDate) return setError("Please choose a date for the update");
    try {
      const payload = { content: newText.trim(), date: newDate };
      const created = await createGoalUpdate(goal.id, payload, apiBase);
      // refresh updates list and select the new one
      await refreshUpdates();
      setSelectedUpdate(created);
      // clear composer
      setNewText("");
      setNewDate("");
      // start polling for analysis automatically (fetchAnalysis will start polling)
    } catch (e: any) {
      setError(e.message || String(e));
    }
  }

//   function agentName(agentId: number) {
//     return agentsMap[agentId] ?? `Agent ${agentId}`;
//   }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="text-sm text-gray-500">Goal</div>
          <div className="text-lg font-semibold text-gray-900">#{goal.id} — {goal.description}</div>
          <div className="mt-1 text-xs text-gray-400">Target: {new Date(goal.target_date).toLocaleDateString()}</div>
        </div>
        <div className="w-48 text-right">
          <div className="text-xs text-gray-500">LLM Market Price</div>
          <div className="mt-1 text-lg font-medium">
            {goal.base_price == null ? (
              <span className="inline-flex items-center gap-2 text-gray-500">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-t-transparent border-gray-400" />
                Pending LLM pricing...
              </span>
            ) : (
              <span>${analysis?.market_price != null?analysis.market_price.toFixed(2):goal.base_price.toFixed(2)}</span>
            )}
          </div>
        </div>
      </div>

      <div className="flex gap-4 h-full">
        {/* Left: timeline */}
        <div className="w-72 overflow-auto">
          <div className="rounded-lg border border-gray-100 bg-white p-3">
            <div className="mb-2 text-sm font-medium">Timeline</div>
            {updates.length === 0 ? (
              <p className="text-sm text-gray-500">No updates yet.</p>
            ) : (
              <ul className="space-y-3">
                {updates.map((u) => (
                  <li key={u.id} className="flex items-start gap-3">
                    <div className="flex-shrink-0 pt-1">
                      <div className={`h-3 w-3 rounded-full ${selectedUpdate?.id === u.id ? "bg-indigo-600" : "bg-gray-300"}`} />
                    </div>
                    <button
                      onClick={() => setSelectedUpdate(u)}
                      className="text-left flex-1 rounded border border-gray-100 p-2 hover:bg-gray-50"
                    >
                      <div className="flex items-center justify-between">
                        <div className="text-sm font-medium text-gray-800">{u.content.slice(0, 48)}{u.content.length > 48 ? "…" : ""}</div>
                        <div className="text-xs text-gray-400">{new Date(u.date).toLocaleDateString()}</div>
                      </div>
                      <div className="mt-1 text-xs text-gray-400">Posted: {u.created_at ? new Date(u.created_at).toLocaleString() : "-"}</div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* composer in left column too for convenience */}
          <div className="mt-3 rounded-lg border border-gray-100 bg-white p-3">
            <form onSubmit={handlePostUpdate} className="space-y-2">
              <div className="text-sm font-medium">Add update</div>
              <textarea
                value={newText}
                onChange={(e) => setNewText(e.target.value)}
                rows={3}
                className="w-full rounded border border-gray-200 px-3 py-2 text-sm"
                placeholder="Short progress update..."
              />
              <div className="flex items-center gap-2">
                <input type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} className="rounded border border-gray-200 px-3 py-2 text-sm" />
                <button type="submit" className="ml-auto rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700">Post</button>
              </div>
              {error && <div className="text-sm text-red-600">{error}</div>}
            </form>
          </div>
        </div>

        {/* Right: details */}
        <div className="flex-1 overflow-auto">
          <div className="rounded-lg border border-gray-100 bg-white p-4">
            {!selectedUpdate ? (
              <p className="text-sm text-gray-500">Select an update to view market analysis and agent thinking.</p>
            ) : (
              <>
                <div className="mb-3 flex items-start justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-gray-800">Update #{selectedUpdate.id}</div>
                    <div className="mt-1 text-xs text-gray-500">{selectedUpdate.content}</div>
                    <div className="mt-1 text-xs text-gray-400">Date: {new Date(selectedUpdate.date).toLocaleDateString()} • Posted: {selectedUpdate.created_at ? new Date(selectedUpdate.created_at).toLocaleString() : "-"}</div>
                  </div>

                  <div className="w-40 text-right text-sm">
                    <div className="text-xs text-gray-500">Market Price (analysis)</div>
                    <div className="mt-1 text-lg font-medium">
                      {analysis?.market_price != null ? (
                        <span>${analysis.market_price.toFixed(2)}</span>
                      ) : loadingAnalysis || polling ? (
                        <span className="inline-flex items-center gap-2 text-gray-500">
                          <span className="h-4 w-4 animate-spin rounded-full border-2 border-t-transparent border-gray-400" /> Analyzing…
                        </span>
                      ) : (
                        <span className="text-sm text-gray-400">No price yet</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Debate / Agent Thinking (collapsible) */}
                <details className="mb-4">
                  <summary className="cursor-pointer text-sm font-medium">Agent Thoughts (expand)</summary>
                  <div className="mt-2 space-y-3">
                    {analysis?.debate_messages?.length ? (
                      <div className="space-y-2">
                        {groupByRound(analysis.debate_messages).map(([round, msgs]) => (
                          <div key={round}>
                            <div className="mb-1 text-xs font-semibold text-gray-600">Round {round}</div>
                            <div className="space-y-2">
                              {msgs.map((m, idx) => (
                                <div key={idx} className="rounded-lg bg-indigo-50 p-3 text-sm text-gray-800">
                                  <div className="text-xs text-indigo-700 font-semibold">{agentDisplayName(m.agent_id)}</div>
                                  <div className="mt-1">{m.content}</div>
                                  <div className="mt-1 text-xs text-gray-400">{new Date(m.timestamp).toLocaleString()}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500">No agent analysis captured yet.</p>
                    )}
                  </div>
                </details>

                {/* Agent spreads */}
                <div className="mb-4">
                  <div className="mb-2 text-sm font-medium">Agent Spreads</div>
                  {analysis?.agent_spreads?.length ? (
                    <div className="grid gap-2 sm:grid-cols-2">
                      {analysis.agent_spreads.map((s, i) => (
                        <div key={i} className="rounded border border-gray-100 p-2 text-sm">
                          <div className="text-xs text-gray-500">{agentDisplayName(s.agent_id)}</div>
                          <div className="mt-1"><strong>Buy:</strong> ${s.buy_price.toFixed(2)} &nbsp; <strong>Sell:</strong> ${s.sell_price.toFixed(2)}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">No spreads yet.</p>
                  )}
                </div>

                {/* Trades */}
                <div>
                  <div className="mb-2 text-sm font-medium">Executed Trades</div>
                  {analysis?.trades?.length ? (
                    <div className="space-y-2">
                      {analysis.trades.map((t, i) => (
                        <div key={i} className="rounded border border-gray-100 p-2 text-sm flex items-center justify-between">
                          <div>
                            <div className="text-xs text-gray-500">{t.timestamp ? new Date(t.timestamp).toLocaleString() : ""}</div>
                            <div className="mt-1"><strong>{t.buyer_name}</strong> bought from <strong>{t.seller_name}</strong></div>
                            <div className="text-xs text-gray-400">Qty: {t.quantity} • ${t.price.toFixed(2)}</div>
                          </div>
                          <div className="text-right text-sm text-gray-700">${(t.price * t.quantity).toFixed(2)}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">No trades executed for this update.</p>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  // helpers
  function agentDisplayName(agentId: number) {
    return agentsMap[agentId] ?? `Agent ${agentId}`;
  }

  function groupByRound(msgs: DebateMessage[]) {
    const byRound = new Map<number, DebateMessage[]>();
    msgs.forEach((m) => {
      const arr = byRound.get(m.round_number) || [];
      arr.push(m);
      byRound.set(m.round_number, arr);
    });
    return Array.from(byRound.entries()).sort((a, b) => a[0] - b[0]);
  }
}
