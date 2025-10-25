
import './App.css'
import { useEffect, useState } from "react";
import { listGoals, createGoal, listGoalUpdates, type Goal } from "./api";
import UpdateDetails from "./components/UpdateDetails";

function toDDMMYYYY(yyyyMmDd: string) {
  if (!yyyyMmDd) return "";
  const [y, m, d] = yyyyMmDd.split("-");
  return `${d}/${m}/${y}`;
}

export default function App() {
  const [apiBase, setApiBase] = useState<string>(() => (import.meta.env.VITE_API_BASE as string) || "http://127.0.0.1:8000");
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<Goal | null>(null);
  const [updatesForSelectedGoal, setUpdatesForSelectedGoal] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  // create form
  const [goalText, setGoalText] = useState("");
  const [measurement, setMeasurement] = useState("");
  const [date, setDate] = useState(""); // YYYY-MM-DD
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadGoals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase]);

  async function loadGoals() {
    setLoading(true);
    setError(null);
    try {
      const data = await listGoals(apiBase);
      setGoals(data);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e?: React.FormEvent) {
    e?.preventDefault();
    setError(null);
    if (!goalText.trim()) return setError("Please enter a goal");
    if (!measurement.trim()) return setError("Please enter a measurement");
    if (!date) return setError("Please select a target date");
    const payload = { goal: goalText.trim(), measurement: measurement.trim(), date: toDDMMYYYY(date) };
    setCreating(true);
    try {
      const created = await createGoal(payload, apiBase);
      setGoals((prev) => [...prev, created].sort((a, b) => a.id - b.id));
      setGoalText("");
      setMeasurement("");
      setDate("");
      // open created goal in drawer and fetch its updates
      setSelectedGoal(created);
      fetchUpdates(created.id);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setCreating(false);
    }
  }

  async function fetchUpdates(goalId: number) {
    try {
      const list = await listGoalUpdates(goalId, apiBase);
      setUpdatesForSelectedGoal(list);
    } catch {
      setUpdatesForSelectedGoal([]);
    }
  }

  async function openGoal(goal: Goal) {
    setSelectedGoal(goal);
    await fetchUpdates(goal.id);
  }

  async function handleGoalUpdated(updated: Goal) {
    // refresh local state
    setGoals((prev) => prev.map((g) => (g.id === updated.id ? updated : g)));
    setSelectedGoal(updated);
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-6xl">
        <header className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Accountability Agent (Market)</h1>
            <p className="text-sm text-gray-500">Create goals and view market analysis per update.</p>
          </div>
          <div className="flex w-full max-w-lg items-center gap-2">
            <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} className="flex-1 rounded border border-gray-200 px-3 py-2 text-sm" />
            <button onClick={loadGoals} className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">Refresh</button>
          </div>
        </header>

        <main className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <section className="col-span-1">
            <form className="rounded-lg bg-white p-4 shadow" onSubmit={handleCreate}>
              <h2 className="mb-3 text-lg font-semibold">Create a Goal</h2>
              <input className="mt-1 w-full rounded border border-gray-200 px-3 py-2 text-sm" placeholder="Goal description" value={goalText} onChange={(e) => setGoalText(e.target.value)} />
              <input className="mt-3 w-full rounded border border-gray-200 px-3 py-2 text-sm" placeholder="Measurement" value={measurement} onChange={(e) => setMeasurement(e.target.value)} />
              <input type="date" className="mt-3 w-full rounded border border-gray-200 px-3 py-2 text-sm" value={date} onChange={(e) => setDate(e.target.value)} />
              <p className="mt-1 text-xs text-gray-400">Server expects DD/MM/YYYY.</p>

              {error && <div className="mt-3 text-sm text-red-600">{error}</div>}

              <div className="mt-4 flex items-center gap-2">
                <button type="submit" disabled={creating} className={`rounded px-4 py-2 text-sm font-medium text-white ${creating ? "bg-gray-400" : "bg-green-600 hover:bg-green-700"}`}>{creating ? "Creating..." : "Create Goal"}</button>
                <button type="button" onClick={() => { setGoalText(""); setMeasurement(""); setDate(""); }} className="rounded border border-gray-200 px-3 py-2 text-sm">Clear</button>
              </div>
            </form>

            <div className="mt-4 rounded-lg bg-white p-4 shadow">
              <h3 className="mb-2 text-sm font-medium">Quick</h3>
              <div className="text-sm text-gray-700">Total goals: <strong>{goals.length}</strong></div>
            </div>
          </section>

          <section className="col-span-2">
            <div className="rounded-lg bg-white p-4 shadow">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold">Goals</h2>
                <div className="text-sm text-gray-500">Total: {goals.length}</div>
              </div>

              {loading ? (
                <div className="space-y-2">
                  <div className="h-4 w-full animate-pulse rounded bg-gray-200" />
                  <div className="h-4 w-3/4 animate-pulse rounded bg-gray-200" />
                </div>
              ) : goals.length === 0 ? (
                <p className="text-sm text-gray-500">No goals yet.</p>
              ) : (
                <ul className="space-y-3">
                  {goals.map((g) => (
                    <li key={g.id} className="rounded border border-gray-100 p-3">
                      <div className="flex items-start justify-between gap-4">
                        <div onClick={() => openGoal(g)} className="cursor-pointer">
                          <div className="text-sm font-medium text-gray-800">#{g.id} — {g.description}</div>
                          <div className="mt-1 text-xs text-gray-500">Target: {new Date(g.target_date).toLocaleDateString()}</div>
                          <div className="mt-1 text-xs text-gray-400">Created: {g.created_at ? new Date(g.created_at).toLocaleString() : "-"}</div>
                        </div>
                        <div className="text-right text-xs">
                          <div className="mb-1">Status</div>
                          <div className={`inline-block rounded px-2 py-1 text-white ${g.status === "active" ? "bg-teal-500" : "bg-gray-400"}`}>{g.status}</div>
                          <div className="mt-2 text-sm">
                            {g.base_price == null ? (
                              <div className="flex items-center gap-2 justify-end">
                                <div className="h-4 w-4 animate-spin rounded-full border-2 border-t-transparent border-gray-400" />
                                <span className="text-xs text-gray-500">Pending</span>
                              </div>
                            ) : (
                              <div className="text-sm font-medium">${g.base_price.toFixed(2)}</div>
                            )}
                          </div>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </main>

        {/* Drawer: simple bottom area showing selected goal details */}
        {selectedGoal && (
          <div className="mt-6 rounded-lg bg-white p-4 shadow">
            <div className="mb-2 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-800">Selected Goal</div>
                <div className="text-xs text-gray-500">#{selectedGoal.id} — {selectedGoal.description}</div>
              </div>
              <div>
                <button onClick={() => { setSelectedGoal(null); setUpdatesForSelectedGoal([]); }} className="rounded px-3 py-1 text-sm font-medium text-gray-600 hover:bg-gray-100">Close</button>
              </div>
            </div>

            <div>
              <UpdateDetails
                apiBase={apiBase}
                goal={selectedGoal}
                initialUpdates={updatesForSelectedGoal}
                onGoalUpdated={(g) => handleGoalUpdated(g)}
                refreshGoalList={loadGoals}
              />
            </div>
          </div>
        )}

        <footer className="mt-6 text-center text-sm text-gray-400">
          <div>Tip: set your API base to where the FastAPI server is running and click Refresh.</div>
        </footer>
      </div>
    </div>
  );
}
