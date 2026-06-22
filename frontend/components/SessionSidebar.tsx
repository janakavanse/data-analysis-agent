"use client";

// Phase 1: hardcoded single session. Step 5 wires to POST/GET /sessions.
export default function SessionSidebar() {
  return (
    <aside className="w-64 bg-gray-100 border-r flex flex-col p-3 flex-shrink-0">
      <button className="mb-3 w-full bg-blue-600 text-white py-1 rounded hover:bg-blue-700 text-sm font-medium">
        + New
      </button>
      <div className="flex flex-col gap-1">
        {/* Phase 1: single hardcoded session, always active */}
        <button className="text-left px-3 py-2 rounded bg-blue-100 text-sm hover:bg-blue-200">
          Session-1
        </button>
      </div>
    </aside>
  );
}
