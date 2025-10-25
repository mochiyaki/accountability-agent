
import './App.css'
import { useEffect, useState, useRef } from "react";

/**
 * App.tsx
 * Vite + React + TypeScript + Tailwind frontend for updated Accountability Agent API
 *
 * Endpoints used:
 * - GET  /goals
 * - POST /goals
 * - GET  /goals/{id}
 * - GET  /goals/{id}/updates
 * - POST /goals/{id}/updates
 */

type Goal = {
  id: number;
  description: string;
  target_date: string; // ISO YYYY-MM-DD
  created_at?: string | null;
  status?: "active" | "resolved";
  payout_amount?: number;
  outcome?: string | null;
  base_price?: number | null;
};

type GoalUpdate = {
  id: number;
  goal_id: number;
  content: string;
  date: string; // ISO date
  created_at?: string | null;
};

type CreateGoalRequest = {
  goal: string;
  measurement: string;
  date: string; // DD/MM/YYYY
};

type CreateGoalUpdateRequest = {
  content: string;
  date: string; // ISO
};

export default function App() {
  const [apiBase, setApiBase] = useState<string>(
    () => (import.meta.env.VITE_API_BASE as string) || "http://127.0.0.1:8000"
  );

  // Create goal form
  const [goalText, setGoalText] = useState("");
  const [measurement, setMeasurement] = useState("");
  const [date, setDate] = useState(""); // YYYY-MM-DD from <input type="date">

  // Goals + UI state
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loadingGoals, setLoadingGoals] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createProgress, setCreateProgress] = useState(0);
  const createInterval = useRef<number | null>(null);

  // Drawer + updates
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<Goal | null>(null);
  const [updates, setUpdates] = useState<GoalUpdate[]>([]);
  const [loadingUpdates, setLoadingUpdates] = useState(false);
  const [newUpdateText, setNewUpdateText] = useState("");
  const [newUpdateDate, setNewUpdateDate] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchGoals();
    return () => {
      if (createInterval.current) window.clearInterval(createInterval.current);
    };
  }, [apiBase]);

  function api(path: string) {
    // ensure no double slashes
    return `${apiBase.replace(/\/+$/, "")}${path.startsWith("/") ? "" : "/"}${path}`;
  }

  async function fetchGoals() {
    setError(null);
    setLoadingGoals(true);
    try {
      const res = await fetch(api("/goals"));
      if (!res.ok) throw new Error(`GET /goals -> ${res.status}`);
      const data: Goal[] = await res.json();
      setGoals(data);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoadingGoals(false);
    }
  }

  // Convert YYYY-MM-DD -> DD/MM/YYYY for backend
  function toDDMMYYYY(yyyyMmDd: string) {
    if (!yyyyMmDd) return "";
    const [y, m, d] = yyyyMmDd.split("-");
    return `${d}/${m}/${y}`;
  }
  function validateDDMMYYYY(v: string) {
    return /^\d{2}\/\d{2}\/\d{4}$/.test(v);
  }

  async function handleCreateGoal(e?: React.FormEvent) {
    e?.preventDefault();
    setError(null);
    if (!goalText.trim()) return setError("Please enter a goal description.");
    if (!measurement.trim()) return setError("Please enter a measurement.");
    if (!date) return setError("Please select a target date.");

    const ddmmyyyy = toDDMMYYYY(date);
    if (!validateDDMMYYYY(ddmmyyyy)) return setError("Date conversion failed.");

    const payload: CreateGoalRequest = {
      goal: goalText.trim(),
      measurement: measurement.trim(),
      date: ddmmyyyy,
    };

    setCreating(true);
    setCreateProgress(8);
    // fake progress loop
    createInterval.current = window.setInterval(() => {
      setCreateProgress((p) => Math.min(96, p + Math.floor(Math.random() * 8) + 2));
    }, 300);

    try {
      const res = await fetch(api("/goals"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`POST /goals -> ${res.status} ${text}`);
      }
      const created: Goal = await res.json();

      setGoals((prev) => {
        if (prev.some((g) => g.id === created.id)) return prev;
        return [...prev, created].sort((a, b) => a.id - b.id);
      });

      setCreateProgress(100);
      setGoalText("");
      setMeasurement("");
      setDate("");

      // open drawer for created goal
      setTimeout(() => {
        setSelectedGoal(created);
        setDrawerOpen(true);
        fetchUpdates(created.id);
      }, 250);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      if (createInterval.current) {
        window.clearInterval(createInterval.current);
        createInterval.current = null;
      }
      setTimeout(() => {
        setCreateProgress(0);
        setCreating(false);
      }, 450);
    }
  }

  async function fetchGoalById(goalId: number) {
    try {
      const res = await fetch(api(`/goals/${goalId}`));
      if (!res.ok) throw new Error(`GET /goals/${goalId} -> ${res.status}`);
      const data: Goal = await res.json();
      setGoals((prev) => prev.map((g) => (g.id === data.id ? data : g)));
      setSelectedGoal(data);
    } catch (e: any) {
      setError(e.message || String(e));
    }
  }

  async function fetchUpdates(goalId: number) {
    setLoadingUpdates(true);
    setError(null);
    try {
      const res = await fetch(api(`/goals/${goalId}/updates`));
      if (!res.ok) throw new Error(`GET /goals/${goalId}/updates -> ${res.status}`);
      const data: GoalUpdate[] = await res.json();
      setUpdates(data);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoadingUpdates(false);
    }
  }

  function openDrawerWithGoal(goal: Goal) {
    setSelectedGoal(goal);
    setDrawerOpen(true);
    fetchUpdates(goal.id);
  }

  async function postUpdate(e?: React.FormEvent) {
    e?.preventDefault();
    if (!selectedGoal) return;
    if (!newUpdateText.trim()) return setError("Please write an update.");
    if (!newUpdateDate) return setError("Please choose a date for the update.");

    const payload: CreateGoalUpdateRequest = {
      content: newUpdateText.trim(),
      date: newUpdateDate,
    };

    try {
      const res = await fetch(api(`/goals/${selectedGoal.id}/updates`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`POST /goals/${selectedGoal.id}/updates -> ${res.status} ${text}`);
      }
      const created: GoalUpdate = await res.json();
      setUpdates((prev) => [created, ...prev]);
      setNewUpdateText("");
      setNewUpdateDate("");
      // refresh goal metadata (base_price etc.)
      fetchGoalById(selectedGoal.id);
    } catch (e: any) {
      setError(e.message || String(e));
    }
  }

  function readableDate(iso?: string | null) {
    if (!iso) return "-";
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch {
      return iso;
    }
  }

  function shortDate(iso: string) {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString();
    } catch {
      return iso;
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-6xl p-6">
        <header className="mb-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Accountability Agent</h1>
            <p className="text-sm text-gray-500">Create goals, receive LLM-backed pricing, and track progress via updates.</p>
          </div>

          <div className="mt-2 flex w-full max-w-lg items-center gap-2 md:mt-0">
            <input
              className="flex-1 rounded border border-gray-200 px-3 py-2 text-sm"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
            />
            <button
              className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              onClick={() => fetchGoals()}
            >
              Refresh
            </button>
          </div>
        </header>

        <main className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {/* Left column: Create form */}
          <section className="col-span-1 md:col-span-1">
            <form className="rounded-lg bg-white p-4 shadow" onSubmit={handleCreateGoal}>
              <h2 className="mb-3 text-lg font-semibold">Create a Goal</h2>

              <label className="block text-sm font-medium text-gray-700">Goal</label>
              <input
                className="mt-1 w-full rounded border border-gray-200 px-3 py-2 text-sm"
                value={goalText}
                onChange={(e) => setGoalText(e.target.value)}
                placeholder="E.g., Run a 10K in under 50 minutes"
              />

              <label className="mt-3 block text-sm font-medium text-gray-700">Measurement</label>
              <input
                className="mt-1 w-full rounded border border-gray-200 px-3 py-2 text-sm"
                value={measurement}
                onChange={(e) => setMeasurement(e.target.value)}
                placeholder="E.g., time in minutes, kg lost, pages written"
              />

              <label className="mt-3 block text-sm font-medium text-gray-700">Target date</label>
              <input
                type="date"
                className="mt-1 w-full rounded border border-gray-200 px-3 py-2 text-sm"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
              <p className="mt-1 text-xs text-gray-400">Date will be sent to the server as <strong>DD/MM/YYYY</strong>.</p>

              {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

              <div className="mt-4 flex items-center gap-2">
                <button
                  type="submit"
                  disabled={creating}
                  className={`inline-flex items-center gap-2 rounded px-4 py-2 text-sm font-medium text-white ${creating ? 'bg-gray-400' : 'bg-green-600 hover:bg-green-700'}`}
                >
                  {creating ? "Creating..." : "Create Goal"}
                </button>

                <button
                  type="button"
                  onClick={() => { setGoalText(""); setMeasurement(""); setDate(""); setError(null); }}
                  className="rounded border border-gray-200 px-3 py-2 text-sm"
                >
                  Clear
                </button>

                <div className="ml-auto w-40">
                  <div className="h-2 w-full overflow-hidden rounded bg-gray-200">
                    <div className="h-full transition-all" style={{ width: `${createProgress}%`, background: 'linear-gradient(90deg,#34d399,#06b6d4)' }} />
                  </div>
                  <p className="mt-1 text-xs text-gray-400">Progress: {Math.round(createProgress)}%</p>
                </div>
              </div>
            </form>

            <div className="mt-4 rounded-lg bg-white p-4 shadow">
              <h3 className="text-sm font-medium text-gray-700">Quick Stats</h3>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-gray-600">
                <div className="rounded border border-gray-100 p-2">Goals<br /><strong className="text-lg text-gray-900">{goals.length}</strong></div>
                <div className="rounded border border-gray-100 p-2">Active<br /><strong className="text-lg text-gray-900">{goals.filter(g => g.status === 'active').length}</strong></div>
              </div>
            </div>
          </section>

          {/* Right: Goals list (spanning two columns) */}
          <section className="col-span-2 md:col-span-2">
            <div className="rounded-lg bg-white p-4 shadow">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold">Goals</h2>
                <div className="text-sm text-gray-500">Total: {goals.length}</div>
              </div>

              {loadingGoals ? (
                <div className="space-y-2">
                  <div className="h-4 w-full animate-pulse rounded bg-gray-200" />
                  <div className="h-4 w-3/4 animate-pulse rounded bg-gray-200" />
                </div>
              ) : goals.length === 0 ? (
                <p className="text-sm text-gray-500">No goals yet — create one to get started.</p>
              ) : (
                <div className="overflow-hidden rounded border border-gray-100">
                  <table className="w-full table-auto text-sm">
                    <thead className="bg-gray-50 text-left text-xs text-gray-500">
                      <tr>
                        <th className="px-3 py-2">#</th>
                        <th className="px-3 py-2">Description</th>
                        <th className="px-3 py-2">Target</th>
                        <th className="px-3 py-2">Base price</th>
                        <th className="px-3 py-2">Status</th>
                        <th className="px-3 py-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y bg-white">
                      {goals.map((g) => (
                        <tr key={g.id}>
                          <td className="px-3 py-2 align-top">{g.id}</td>
                          <td className="px-3 py-2 align-top">{g.description}</td>
                          <td className="px-3 py-2 align-top">{new Date(g.target_date).toLocaleDateString()}</td>
                          <td className="px-3 py-2 align-top">
                            {g.base_price == null ? (
                              <div className="flex items-center gap-2">
                                <div className="h-4 w-4 animate-spin rounded-full border-2 border-t-transparent border-gray-400" />
                                <span className="text-xs text-gray-500">Pending LLM pricing...</span>
                              </div>
                            ) : (
                              <span className="text-sm font-medium text-gray-900">${g.base_price.toFixed(2)}</span>
                            )}
                          </td>
                          <td className="px-3 py-2 align-top">{g.status}</td>
                          <td className="px-3 py-2 align-top">
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => openDrawerWithGoal(g)}
                                className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700"
                              >
                                View
                              </button>
                              <button
                                onClick={() => fetchGoalById(g.id)}
                                className="rounded border border-gray-200 px-3 py-1 text-xs"
                              >
                                Refresh
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
            </div>
          </section>
        </main>

        {/* Slide-in drawer */}
        <div className={`fixed inset-y-0 right-0 z-40 w-full max-w-md transform bg-white shadow-xl transition-transform ${drawerOpen ? "translate-x-0" : "translate-x-full"}`}>
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div>
                <h3 className="text-lg font-semibold">Goal Details</h3>
                <p className="text-xs text-gray-500">Details & updates</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => { setDrawerOpen(false); setSelectedGoal(null); setUpdates([]); }}
                  className="rounded px-3 py-1 text-sm font-medium text-gray-600 hover:bg-gray-100"
                >
                  Close
                </button>
              </div>
            </div>

            <div className="overflow-y-auto p-4">
              {!selectedGoal ? (
                <p className="text-sm text-gray-500">No goal selected.</p>
              ) : (
                <div className="space-y-4">
                  <div className="rounded border border-gray-100 p-3">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-sm font-medium text-gray-800">#{selectedGoal.id} — {selectedGoal.description}</div>
                        <div className="mt-1 text-xs text-gray-500">Target: {shortDate(selectedGoal.target_date)}</div>
                        <div className="mt-1 text-xs text-gray-400">Created: {readableDate(selectedGoal.created_at)}</div>
                      </div>
                      <div className="text-right text-xs">
                        <div className="mb-1">Status</div>
                        <div className={`inline-block rounded px-2 py-1 text-white ${selectedGoal.status === "active" ? "bg-teal-500" : "bg-gray-400"}`}>{selectedGoal.status}</div>
                      </div>
                    </div>

                    <div className="mt-3 flex items-center justify-between gap-4">
                      <div>
                        <div className="text-xs text-gray-500">Payout</div>
                        <div className="text-sm font-medium">${selectedGoal.payout_amount ?? 100}</div>
                      </div>

                      <div>
                        <div className="text-xs text-gray-500">LLM Base Price</div>
                        <div className="text-sm font-medium">
                          {selectedGoal.base_price == null ? (
                            <div className="flex items-center gap-2">
                              <div className="h-4 w-4 animate-spin rounded-full border-2 border-t-transparent border-gray-400" />
                              <span className="text-gray-500 text-sm">Pending LLM pricing...</span>
                            </div>
                          ) : (
                            <span>${selectedGoal.base_price.toFixed(2)}</span>
                          )}
                        </div>
                      </div>

                      <div>
                        <div className="text-xs text-gray-500">Outcome</div>
                        <div className="text-sm">{selectedGoal.outcome ?? "Unresolved"}</div>
                      </div>
                    </div>
                  </div>

                  {/* Compose update */}
                  <form onSubmit={postUpdate} className="rounded border border-gray-100 p-3">
                    <h4 className="text-sm font-medium">Add an update</h4>
                    <textarea
                      value={newUpdateText}
                      onChange={(e) => setNewUpdateText(e.target.value)}
                      className="mt-2 w-full rounded border border-gray-200 px-3 py-2 text-sm"
                      rows={3}
                      placeholder="What did you do today toward this goal?"
                    />
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        type="date"
                        value={newUpdateDate}
                        onChange={(e) => setNewUpdateDate(e.target.value)}
                        className="rounded border border-gray-200 px-3 py-2 text-sm"
                      />
                      <button className="ml-auto rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700">Post Update</button>
                    </div>
                  </form>

                  {/* Chat bubble style timeline */}
                  <div>
                    <h4 className="mb-2 text-sm font-medium">Updates</h4>
                    {loadingUpdates ? (
                      <div className="space-y-2">
                        <div className="h-8 w-3/4 animate-pulse rounded bg-gray-200" />
                        <div className="h-8 w-1/2 animate-pulse rounded bg-gray-200" />
                      </div>
                    ) : updates.length === 0 ? (
                      <p className="text-sm text-gray-500">No updates yet — be the first to add one.</p>
                    ) : (
                      <div className="space-y-3">
                        {updates.map((u) => (
                          <div key={u.id} className="flex gap-3">
                            <div className="flex-shrink-0">
                              <div className="h-8 w-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-semibold">
                                {String(u.content || "U").charAt(0).toUpperCase()}
                              </div>
                            </div>
                            <div>
                              <div className="rounded-lg bg-indigo-50 p-3 text-sm text-gray-800">
                                {u.content}
                              </div>
                              <div className="mt-1 text-xs text-gray-400">{shortDate(u.date)} — {readableDate(u.created_at)}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <footer className="mt-8 text-center text-sm text-gray-400">
          <div>Tip: set your API base to where the FastAPI server is running and click Refresh.</div>
        </footer>
      </div>
    </div>
  );
}
