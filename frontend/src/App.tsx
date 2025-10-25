
import './App.css'
import { useEffect, useState } from "react";
// App.tsx
// Vite + React + TypeScript + TailwindCSS frontend for the provided FastAPI backend

type Goal = {
  id: number;
  description: string;
  target_date: string; // ISO date string
  created_at?: string;
  status?: string;
};

type Contract = {
  id: number;
  goal_id: number;
  created_at?: string;
  status?: string;
};

type CreateGoalRequest = {
  goal: string;
  measurement: string;
  date: string; // DD/MM/YYYY
};

export default function App() {
  const [apiBase, setApiBase] = useState<string>(
    () => (import.meta.env.VITE_API_BASE as string) || "http://127.0.0.1:8000"
  );
  const [goalText, setGoalText] = useState("");
  const [measurement, setMeasurement] = useState("");
  const [date, setDate] = useState(""); // will bind to <input type=date> (YYYY-MM-DD)

  const [goals, setGoals] = useState<Goal[]>([]);
  const [lastCreatedContract, setLastCreatedContract] = useState<Contract | null>(null);

  const [loadingGoals, setLoadingGoals] = useState(false);
  const [creating, setCreating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchGoals();
  }, [apiBase]);

  async function fetchGoals() {
    setLoadingGoals(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase.replace(/\/+$/, "")}/goals`);
      if (!res.ok) throw new Error(`GET /goals returned ${res.status}`);
      const data: Goal[] = await res.json();
      setGoals(data);
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setLoadingGoals(false);
    }
  }

  function isoToReadable(iso?: string) {
    if (!iso) return "-";
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch (e) {
      return iso;
    }
  }

  // converts YYYY-MM-DD to DD/MM/YYYY
  function formatDateForApi(yyyyMmDd: string) {
    if (!yyyyMmDd) return "";
    const [y, m, d] = yyyyMmDd.split("-");
    return `${d}/${m}/${y}`;
  }

  function validateDDMMYYYY(v: string) {
    return /^\d{2}\/\d{2}\/\d{4}$/.test(v);
  }

  async function handleCreate(e?: React.FormEvent) {
    e?.preventDefault();
    setError(null);

    if (!goalText.trim()) return setError("Please enter a goal description.");
    if (!measurement.trim()) return setError("Please enter a measurement for the goal.");
    if (!date) return setError("Please pick a target date.");

    const ddmmyyyy = formatDateForApi(date);
    if (!validateDDMMYYYY(ddmmyyyy)) return setError("Converted date is invalid (expected DD/MM/YYYY).");

    const payload: CreateGoalRequest = {
      goal: goalText.trim(),
      measurement: measurement.trim(),
      date: ddmmyyyy,
    };

    setCreating(true);
    setProgress(6);
    // fake progress animation until request returns
    const progressInterval = setInterval(() => {
      setProgress((p) => Math.min(96, p + Math.random() * 12));
    }, 350);

    try {
      const res = await fetch(`${apiBase.replace(/\/+$/, "")}/goals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`POST /goals failed: ${res.status} ${text}`);
      }
      const json = await res.json();

      // backend returns { goal: Goal, contract: Contract }
      const createdGoal: Goal = json.goal;
      const contract: Contract = json.contract;
      setLastCreatedContract(contract ?? null);

      // update local goals list (re-fetching is optional but ensures consistency)
      setGoals((prev) => {
        // avoid duplicate
        if (prev.some((g) => g.id === createdGoal.id)) return prev;
        return [...prev, createdGoal].sort((a, b) => a.id - b.id);
      });

      // success UI
      setProgress(100);
      setGoalText("");
      setMeasurement("");
      setDate("");
    } catch (err: any) {
      setError(err.message || String(err));
      setProgress(0);
    } finally {
      clearInterval(progressInterval);
      // small delay so UI shows 100% briefly
      setTimeout(() => {
        setCreating(false);
        setProgress(0);
      }, 450);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6">
          <h1 className="text-3xl font-extrabold text-gray-900">Accountability Agent</h1>
          <p className="mt-1 text-sm text-gray-600">Create goals, mint simple contracts and track them.</p>
        </header>

        <section className="mb-6 rounded-lg bg-white p-6 shadow">
          <label className="block text-xs font-medium text-gray-500">API Base</label>
          <div className="mt-2 flex gap-2">
            <input
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              className="flex-1 rounded border border-gray-200 px-3 py-2 text-sm"
            />
            <button
              onClick={fetchGoals}
              className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Refresh
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-400">Default: http://127.0.0.1:8000</p>
        </section>

        <section className="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2">
          <form
            className="rounded-lg bg-white p-6 shadow"
            onSubmit={handleCreate}
            noValidate
          >
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

            <label className="mt-3 block text-sm font-medium text-gray-700">Target Date</label>
            <input
              type="date"
              className="mt-1 w-full rounded border border-gray-200 px-3 py-2 text-sm"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
            <p className="mt-1 text-xs text-gray-400">We will send the date to the API in DD/MM/YYYY format.</p>

            {error && <div className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">{error}</div>}

            <div className="mt-4 flex items-center gap-3">
              <button
                type="submit"
                className={`inline-flex items-center rounded px-4 py-2 text-sm font-medium text-white ${creating ? 'bg-gray-400' : 'bg-green-600 hover:bg-green-700'}`}
                disabled={creating}
              >
                {creating ? 'Creating...' : 'Create Goal'}
              </button>

              <button
                type="button"
                onClick={() => { setGoalText(''); setMeasurement(''); setDate(''); setError(null); }}
                className="rounded border border-gray-200 px-3 py-2 text-sm"
              >
                Clear
              </button>

              <div className="ml-auto max-w-xs flex-1">
                <div className="h-2 w-full overflow-hidden rounded bg-gray-200">
                  <div
                    className="h-full transition-all"
                    style={{ width: `${progress}%`, background: 'linear-gradient(90deg,#34d399,#06b6d4)' }}
                  />
                </div>
                <p className="mt-1 text-xs text-gray-400">Progress: {Math.round(progress)}%</p>
              </div>
            </div>

            {lastCreatedContract && (
              <div className="mt-4 rounded border border-green-100 bg-green-50 p-3 text-sm text-green-800">
                Created contract <strong>#{lastCreatedContract.id}</strong> for goal <strong>#{lastCreatedContract.goal_id}</strong>.
              </div>
            )}
          </form>

          <div className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-3 text-lg font-semibold">Goals</h2>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <button
                  className="rounded bg-indigo-600 px-3 py-1 text-sm font-medium text-white hover:bg-indigo-700"
                  onClick={fetchGoals}
                  disabled={loadingGoals}
                >
                  Refresh
                </button>
                <button
                  className="rounded border border-gray-200 px-3 py-1 text-sm"
                  onClick={() => setGoals([])}
                >
                  Clear List
                </button>
              </div>
              <div className="text-sm text-gray-500">Total: {goals.length}</div>
            </div>

            {loadingGoals ? (
              <div className="space-y-2">
                <div className="h-3 w-3/4 animate-pulse rounded bg-gray-200" />
                <div className="h-3 w-1/2 animate-pulse rounded bg-gray-200" />
              </div>
            ) : goals.length === 0 ? (
              <p className="text-sm text-gray-500">No goals yet. Create one on the left.</p>
            ) : (
              <ul className="space-y-3">
                {goals.map((g) => (
                  <li key={g.id} className="rounded border border-gray-100 p-3">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-sm font-medium text-gray-800">#{g.id} — {g.description}</div>
                        <div className="mt-1 text-xs text-gray-500">Target: {new Date(g.target_date).toLocaleDateString()}</div>
                        <div className="mt-1 text-xs text-gray-400">Created: {isoToReadable(g.created_at)}</div>
                      </div>
                      <div className="flex flex-col items-end text-xs text-gray-500">
                        <div className="mb-1 rounded px-2 py-1 text-white" style={{ background: g.status === 'active' ? '#06b6d4' : '#94a3b8' }}>{g.status}</div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}

            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
          </div>
        </section>

        <footer className="mt-6 text-center text-sm text-gray-400">
          <div>Tip: set your API base to where the FastAPI server is running and click Refresh.</div>
        </footer>
      </div>
    </div>
  );
}
