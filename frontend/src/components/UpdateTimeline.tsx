// src/components/UpdateTimeline.tsx
// import React from "react";

import type { GoalUpdate } from "../api";

type Props = {
  updates: GoalUpdate[];
  selectedUpdateId?: number | null;
  onSelect: (u: GoalUpdate) => void;
};

export default function UpdateTimeline({ updates, selectedUpdateId, onSelect }: Props) {
  return (
    <div>
      <h4 className="mb-2 text-sm font-medium">Updates</h4>
      {updates.length === 0 ? (
        <p className="text-sm text-gray-500">No updates yet.</p>
      ) : (
        <ul className="space-y-3">
          {updates.map((u) => (
            <li key={u.id} className="flex items-start gap-3">
              {/* left dot */}
              <div className="flex-shrink-0 pt-1">
                <div
                  className={`h-3 w-3 rounded-full ${selectedUpdateId === u.id ? "bg-indigo-600" : "bg-gray-300"}`}
                />
              </div>

              <button
                onClick={() => onSelect(u)}
                className="text-left flex-1 rounded border border-gray-100 p-3 hover:bg-gray-50"
              >
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-gray-800">{u.content.slice(0, 60)}{u.content.length > 60 ? "…" : ""}</div>
                  <div className="text-xs text-gray-400">{new Date(u.date).toLocaleDateString()}</div>
                </div>
                <div className="mt-1 text-xs text-gray-500">Posted: {u.created_at ? new Date(u.created_at).toLocaleString() : "-"}</div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
